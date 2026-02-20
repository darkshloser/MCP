"""MCP Server - FastAPI Application.

The MCP Server is the authoritative component for tool execution.
It has no LLM or UI logic - only tool registration, authorization,
routing, and auditing.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from shared.config import Settings, get_settings
from shared.logging import get_logger, setup_logging
from shared.models import (
    ExecutionContext,
    ToolCall,
    ToolResult,
    ToolResultStatus,
    UserContext,
)
from mcp_server.auth import AuthConfig, AuthMiddleware
from mcp_server.audit import get_audit_logger
from mcp_server.registry import get_registry
from mcp_server.router import AsyncToolRouter

# Will be initialized at startup
from domains import load_all_domains

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


# Request/Response Models
class ToolCallRequest(BaseModel):
    """Request to execute a tool."""
    tool_name: str = Field(..., description="Fully-qualified tool name")
    parameters: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = Field(default=None)
    correlation_id: Optional[str] = Field(default=None)


class ToolCallResponse(BaseModel):
    """Response from tool execution."""
    tool_name: str
    status: str
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    execution_time_ms: float = 0


class ToolListResponse(BaseModel):
    """List of available tools."""
    tools: list[dict[str, Any]]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    domains: list[str]
    tool_count: int


# Global instances
_settings: Optional[Settings] = None
_auth_middleware: Optional[AuthMiddleware] = None
_router: Optional[AsyncToolRouter] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _settings, _auth_middleware, _router
    
    # Startup
    logger.info("Starting MCP Server")
    
    _settings = get_settings()
    setup_logging(_settings.log_level, json_output=_settings.environment == "production")
    
    # Initialize auth
    _auth_middleware = AuthMiddleware(AuthConfig(
        secret_key=_settings.orchestrator.secret_key,
        token_expire_minutes=_settings.orchestrator.token_expire_minutes,
        trusted_clients=_settings.mcp_server.trusted_clients,
        require_auth=_settings.mcp_server.require_auth,
    ))
    
    # Initialize router with audit logger
    audit_logger = get_audit_logger(
        log_path=_settings.mcp_server.audit_log_path,
        enabled=_settings.mcp_server.enable_audit
    )
    _router = AsyncToolRouter(
        registry=get_registry(),
        audit_logger=audit_logger
    )
    
    # Load all domains
    load_all_domains(_router)
    
    registry = get_registry()
    logger.info(
        "MCP Server started",
        domains=registry.list_domains(),
        tool_count=sum(registry.get_tool_count().values())
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down MCP Server")
    await audit_logger.flush()


# Create FastAPI app
app = FastAPI(
    title="MCP Server",
    description="MCP-based tool execution server",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserContext:
    """Dependency to get current authenticated user."""
    if _auth_middleware is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server not initialized"
        )
    
    if not _settings.mcp_server.require_auth:
        return UserContext(
            user_id="anonymous",
            username="anonymous",
            roles=["user"],
        )
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = _auth_middleware.verify_token(credentials.credentials)
    return _auth_middleware.get_user_context(token_data)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    registry = get_registry()
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        domains=registry.list_domains(),
        tool_count=sum(registry.get_tool_count().values())
    )


@app.get("/tools", response_model=ToolListResponse, tags=["Tools"])
async def list_tools(
    domain: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """
    List all available tools.
    
    Optionally filter by domain. Returns tools formatted for LLM consumption.
    """
    registry = get_registry()
    
    domains = [domain] if domain else None
    tools = registry.get_tools_for_llm(domains=domains, user_roles=user.roles)
    
    return ToolListResponse(tools=tools, count=len(tools))


@app.get("/tools/{tool_name}", tags=["Tools"])
async def get_tool(
    tool_name: str,
    user: UserContext = Depends(get_current_user)
):
    """Get details for a specific tool."""
    registry = get_registry()
    tool = registry.get(tool_name)
    
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found"
        )
    
    return tool.model_dump()


@app.post("/execute", response_model=ToolCallResponse, tags=["Execution"])
async def execute_tool(
    request: ToolCallRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Execute a tool.
    
    This is the main endpoint for tool execution.
    Handles validation, authorization, routing, and auditing.
    """
    if _router is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server not initialized"
        )
    
    # Create execution context
    context = ExecutionContext(
        request_id=request.request_id or str(uuid.uuid4()),
        user=user,
        timestamp=datetime.utcnow(),
        source="mcp_client",
        correlation_id=request.correlation_id,
    )
    
    # Create tool call
    call = ToolCall(
        tool_name=request.tool_name,
        parameters=request.parameters,
        context=context
    )
    
    # Execute
    result = await _router.execute(call)
    
    # Convert to response
    return ToolCallResponse(
        tool_name=result.tool_name,
        status=result.status.value,
        data=result.data,
        error=result.error,
        error_code=result.error_code,
        execution_time_ms=result.execution_time_ms
    )


@app.get("/domains", tags=["Domains"])
async def list_domains(user: UserContext = Depends(get_current_user)):
    """List all registered domains."""
    registry = get_registry()
    domains = registry.list_domains()
    counts = registry.get_tool_count()
    
    return {
        "domains": [
            {"name": d, "tool_count": counts.get(d, 0)}
            for d in domains
        ]
    }


def main():
    """Run the MCP Server."""
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "mcp_server.main:app",
        host=settings.mcp_server.host,
        port=settings.mcp_server.port,
        reload=settings.environment == "development"
    )


if __name__ == "__main__":
    main()
