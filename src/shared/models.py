"""Core data models for MCP Platform.

This module defines all shared data structures used across the platform,
ensuring type safety and validation throughout the system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExecutionType(str, Enum):
    """Type of tool execution - read operations vs write operations."""
    READ = "read"
    WRITE = "write"


class PermissionLevel(str, Enum):
    """Permission levels for tool access."""
    PUBLIC = "public"
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class Permission(BaseModel):
    """Permission definition for tool access control."""
    level: PermissionLevel = Field(default=PermissionLevel.USER)
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class ToolParameter(BaseModel):
    """Definition of a single tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[list[Any]] = None


class ToolDefinition(BaseModel):
    """
    Complete definition of an MCP tool.
    
    Tools must be declarative, versioned, and discoverable.
    All tools are namespaced per domain (e.g., hr.get_employee).
    """
    name: str = Field(..., description="Fully-qualified tool name (domain.action)")
    domain: str = Field(..., description="Domain namespace")
    description: str = Field(..., description="Clear description for LLM usage")
    version: str = Field(default="1.0.0")
    
    # Schema definitions
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for input validation"
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for output structure"
    )
    
    # Execution metadata
    execution_type: ExecutionType = Field(default=ExecutionType.READ)
    permissions: Permission = Field(default_factory=Permission)
    
    # Additional metadata
    tags: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    deprecated: bool = False
    
    @property
    def qualified_name(self) -> str:
        """Return the fully qualified tool name."""
        return f"{self.domain}.{self.name}" if "." not in self.name else self.name


class UserContext(BaseModel):
    """Authenticated user context propagated through the system."""
    user_id: str
    username: str
    email: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """
    Complete context for tool execution.
    
    Contains user identity, request metadata, and execution parameters.
    """
    request_id: str = Field(..., description="Unique request identifier")
    user: UserContext
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(default="orchestrator", description="Request source")
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None


class ToolCall(BaseModel):
    """
    A request to execute a specific tool.
    
    Contains the tool identifier, parameters, and execution context.
    """
    tool_name: str = Field(..., description="Fully-qualified tool name")
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: ExecutionContext


class ToolResultStatus(str, Enum):
    """Status of tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"


class ToolResult(BaseModel):
    """
    Result of a tool execution.
    
    Contains the output data, status, and any error information.
    """
    tool_name: str
    status: ToolResultStatus
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    execution_time_ms: float = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEntry(BaseModel):
    """
    Audit log entry for tool executions.
    
    Captures user, tool, parameters, timestamp, and result for compliance.
    """
    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # User information
    user_id: str
    username: str
    
    # Tool information
    tool_name: str
    domain: str
    execution_type: ExecutionType
    
    # Request details
    parameters: dict[str, Any] = Field(default_factory=dict)
    
    # Result information
    status: ToolResultStatus
    error: Optional[str] = None
    execution_time_ms: float = 0
    
    # Correlation
    request_id: str
    correlation_id: Optional[str] = None


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    role: str = Field(..., description="Message role: user, assistant, system, tool")
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Conversation(BaseModel):
    """Conversation state maintained by the orchestrator."""
    id: str
    user: UserContext
    messages: list[ConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Response from the LLM layer."""
    content: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    finish_reason: str = "stop"
    usage: dict[str, int] = Field(default_factory=dict)


class DomainConfig(BaseModel):
    """Configuration for an application domain."""
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = True
    
    # Connection settings
    base_url: Optional[str] = None
    auth_type: Optional[str] = None
    
    # Rate limiting
    rate_limit_rpm: int = 60
    timeout_seconds: int = 30
    
    # Feature flags
    features: dict[str, bool] = Field(default_factory=dict)
