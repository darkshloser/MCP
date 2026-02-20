"""Audit logging for MCP Server.

Logs all tool executions for compliance and debugging.
Captures: user, tool, parameters, timestamp, result.
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiofiles

from shared.logging import get_logger
from shared.models import (
    AuditEntry,
    ExecutionContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
)

logger = get_logger(__name__)


class AuditLogger:
    """
    Audit logger for MCP tool executions.
    
    All tool executions are logged with:
    - User identity
    - Tool name and domain
    - Parameters (with sensitive data redaction)
    - Timestamp
    - Result status
    """
    
    # Parameters that should be redacted in audit logs
    SENSITIVE_PARAMS = {"password", "token", "secret", "api_key", "apikey", "credential"}
    
    def __init__(
        self,
        log_path: str = "logs/audit.log",
        enabled: bool = True,
        buffer_size: int = 100
    ) -> None:
        self.log_path = Path(log_path)
        self.enabled = enabled
        self.buffer_size = buffer_size
        self._buffer: list[AuditEntry] = []
        self._lock = asyncio.Lock()
        
        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _redact_sensitive(self, params: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive parameters from audit logs."""
        redacted = {}
        for key, value in params.items():
            if key.lower() in self.SENSITIVE_PARAMS:
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive(value)
            else:
                redacted[key] = value
        return redacted
    
    def create_entry(
        self,
        tool: ToolDefinition,
        call: ToolCall,
        result: ToolResult
    ) -> AuditEntry:
        """
        Create an audit entry from tool execution data.
        
        Args:
            tool: Tool definition
            call: Tool call request
            result: Tool execution result
        
        Returns:
            Audit entry
        """
        return AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            user_id=call.context.user.user_id,
            username=call.context.user.username,
            tool_name=tool.qualified_name,
            domain=tool.domain,
            execution_type=tool.execution_type,
            parameters=self._redact_sensitive(call.parameters),
            status=result.status,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
            request_id=call.context.request_id,
            correlation_id=call.context.correlation_id,
        )
    
    async def log(
        self,
        tool: ToolDefinition,
        call: ToolCall,
        result: ToolResult
    ) -> None:
        """
        Log a tool execution.
        
        Args:
            tool: Tool definition
            call: Tool call request
            result: Tool execution result
        """
        if not self.enabled:
            return
        
        entry = self.create_entry(tool, call, result)
        
        # Log to structured logger immediately
        logger.info(
            "Tool executed",
            audit_id=entry.id,
            user=entry.username,
            tool=entry.tool_name,
            domain=entry.domain,
            status=entry.status.value,
            execution_time_ms=entry.execution_time_ms
        )
        
        # Buffer for batch file writing
        async with self._lock:
            self._buffer.append(entry)
            
            if len(self._buffer) >= self.buffer_size:
                await self._flush()
    
    async def _flush(self) -> None:
        """Flush buffered entries to file."""
        if not self._buffer:
            return
        
        entries_to_write = self._buffer.copy()
        self._buffer.clear()
        
        try:
            async with aiofiles.open(self.log_path, "a") as f:
                for entry in entries_to_write:
                    line = entry.model_dump_json() + "\n"
                    await f.write(line)
        except Exception as e:
            logger.error("Failed to write audit log", error=str(e))
            # Re-add entries to buffer for retry
            self._buffer.extend(entries_to_write)
    
    async def flush(self) -> None:
        """Public method to flush audit buffer."""
        async with self._lock:
            await self._flush()
    
    async def query(
        self,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[ToolResultStatus] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> list[AuditEntry]:
        """
        Query audit logs with filters.
        
        This is a simple file-based implementation.
        In production, use a database or log aggregation service.
        
        Args:
            user_id: Filter by user ID
            tool_name: Filter by tool name
            domain: Filter by domain
            status: Filter by status
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum entries to return
        
        Returns:
            List of matching audit entries
        """
        results: list[AuditEntry] = []
        
        if not self.log_path.exists():
            return results
        
        try:
            async with aiofiles.open(self.log_path, "r") as f:
                async for line in f:
                    if len(results) >= limit:
                        break
                    
                    try:
                        data = json.loads(line.strip())
                        entry = AuditEntry(**data)
                        
                        # Apply filters
                        if user_id and entry.user_id != user_id:
                            continue
                        if tool_name and entry.tool_name != tool_name:
                            continue
                        if domain and entry.domain != domain:
                            continue
                        if status and entry.status != status:
                            continue
                        if start_time and entry.timestamp < start_time:
                            continue
                        if end_time and entry.timestamp > end_time:
                            continue
                        
                        results.append(entry)
                        
                    except (json.JSONDecodeError, ValueError):
                        continue
        
        except Exception as e:
            logger.error("Failed to query audit log", error=str(e))
        
        return results


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(log_path: str = "logs/audit.log", enabled: bool = True) -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(log_path=log_path, enabled=enabled)
    return _audit_logger
