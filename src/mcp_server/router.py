"""Tool Router for MCP Server.

Routes tool calls to appropriate domain adapters.
Handles validation, authorization, and execution.
"""

import time
import uuid
from typing import Any, Callable, Optional

from shared.logging import get_logger
from shared.models import (
    ExecutionContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
    UserContext,
)
from mcp_server.auth import authorize_request
from mcp_server.audit import AuditLogger, get_audit_logger
from mcp_server.registry import ToolRegistry, get_registry

logger = get_logger(__name__)


# Type alias for adapter execute functions
AdapterExecutor = Callable[[str, dict[str, Any], ExecutionContext], ToolResult]


class ToolRouter:
    """
    Routes tool calls to appropriate domain adapters.
    
    Responsibilities:
    - Validate tool calls against schemas
    - Authorize requests
    - Route to appropriate adapter
    - Audit all executions
    """
    
    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        audit_logger: Optional[AuditLogger] = None
    ) -> None:
        self.registry = registry or get_registry()
        self.audit_logger = audit_logger or get_audit_logger()
        self._adapters: dict[str, AdapterExecutor] = {}
    
    def register_adapter(self, domain: str, executor: AdapterExecutor) -> None:
        """
        Register a domain adapter.
        
        Args:
            domain: Domain name
            executor: Function that executes tools for this domain
        """
        self._adapters[domain] = executor
        logger.info("Adapter registered", domain=domain)
    
    def unregister_adapter(self, domain: str) -> bool:
        """
        Unregister a domain adapter.
        
        Args:
            domain: Domain name
        
        Returns:
            True if removed, False if not found
        """
        if domain in self._adapters:
            del self._adapters[domain]
            logger.info("Adapter unregistered", domain=domain)
            return True
        return False
    
    async def execute(self, call: ToolCall) -> ToolResult:
        """
        Execute a tool call.
        
        This is the main entry point for tool execution.
        Handles validation, authorization, routing, and auditing.
        
        Args:
            call: Tool call request
        
        Returns:
            Tool execution result
        """
        start_time = time.time()
        tool_name = call.tool_name
        
        logger.debug(
            "Executing tool",
            tool=tool_name,
            user=call.context.user.user_id,
            request_id=call.context.request_id
        )
        
        # Look up tool
        tool = self.registry.get(tool_name)
        if not tool:
            result = ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.NOT_FOUND,
                error=f"Tool '{tool_name}' not found",
                error_code="TOOL_NOT_FOUND"
            )
            return result
        
        # Validate input
        is_valid, errors = self.registry.validate_input(tool_name, call.parameters)
        if not is_valid:
            result = ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.VALIDATION_ERROR,
                error=f"Validation failed: {'; '.join(errors)}",
                error_code="VALIDATION_ERROR"
            )
            await self.audit_logger.log(tool, call, result)
            return result
        
        # Authorize request
        authorized, auth_error = authorize_request(tool, call.context.user, call.context)
        if not authorized:
            result = ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.UNAUTHORIZED,
                error=auth_error or "Unauthorized",
                error_code="UNAUTHORIZED"
            )
            await self.audit_logger.log(tool, call, result)
            return result
        
        # Get adapter
        adapter = self._adapters.get(tool.domain)
        if not adapter:
            result = ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=f"No adapter registered for domain '{tool.domain}'",
                error_code="NO_ADAPTER"
            )
            await self.audit_logger.log(tool, call, result)
            return result
        
        # Execute via adapter
        try:
            result = await self._execute_with_adapter(
                adapter, tool, call.parameters, call.context
            )
        except Exception as e:
            logger.error(
                "Tool execution failed",
                tool=tool_name,
                error=str(e),
                exc_info=True
            )
            result = ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )
        
        # Calculate execution time
        result.execution_time_ms = (time.time() - start_time) * 1000
        
        # Audit the execution
        await self.audit_logger.log(tool, call, result)
        
        return result
    
    async def _execute_with_adapter(
        self,
        adapter: AdapterExecutor,
        tool: ToolDefinition,
        parameters: dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        Execute a tool using its domain adapter.
        
        Args:
            adapter: Domain adapter executor function
            tool: Tool definition
            parameters: Tool parameters
            context: Execution context
        
        Returns:
            Tool execution result
        """
        # Extract action name from qualified tool name
        action = tool.name.split(".")[-1] if "." in tool.name else tool.name
        
        # Call adapter
        try:
            result = adapter(action, parameters, context)
            
            # If adapter returns a dict, wrap in ToolResult
            if isinstance(result, dict):
                return ToolResult(
                    tool_name=tool.qualified_name,
                    status=ToolResultStatus.SUCCESS,
                    data=result
                )
            
            # If adapter returns ToolResult directly
            if isinstance(result, ToolResult):
                return result
            
            # Wrap any other return value
            return ToolResult(
                tool_name=tool.qualified_name,
                status=ToolResultStatus.SUCCESS,
                data=result
            )
            
        except Exception as e:
            raise


class AsyncToolRouter(ToolRouter):
    """
    Async-aware tool router for async adapters.
    """
    
    async def _execute_with_adapter(
        self,
        adapter: AdapterExecutor,
        tool: ToolDefinition,
        parameters: dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """Execute with support for async adapters."""
        import asyncio
        
        action = tool.name.split(".")[-1] if "." in tool.name else tool.name
        
        # Check if adapter is async
        if asyncio.iscoroutinefunction(adapter):
            result = await adapter(action, parameters, context)
        else:
            # Run sync adapter in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, adapter, action, parameters, context
            )
        
        # Normalize result
        if isinstance(result, dict):
            return ToolResult(
                tool_name=tool.qualified_name,
                status=ToolResultStatus.SUCCESS,
                data=result
            )
        
        if isinstance(result, ToolResult):
            return result
        
        return ToolResult(
            tool_name=tool.qualified_name,
            status=ToolResultStatus.SUCCESS,
            data=result
        )
