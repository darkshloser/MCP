"""Orchestrator - FastAPI Application.

The Orchestrator (AI Gateway) provides:
- Chat API for frontend
- Conversation management
- LLM integration
- MCP Client orchestration
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from shared.config import Settings, get_settings
from shared.logging import get_logger, setup_logging
from shared.models import UserContext
from mcp_client.client import MCPClient
from mcp_server.auth import AuthConfig, AuthMiddleware
from orchestrator.llm import create_llm_provider
from orchestrator.conversation import ConversationManager
from orchestrator.gateway import AIGateway

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request from frontend."""
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(default=None, description="Existing conversation ID")
    domains: Optional[list[str]] = Field(default=None, description="Allowed tool domains")


class ChatResponse(BaseModel):
    """Chat response to frontend."""
    conversation_id: str
    response: str
    request_id: str


class ConversationListResponse(BaseModel):
    """List of conversations."""
    conversations: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    mcp_server: str
    tool_count: int
    conversation_count: int


# Global instances
_settings: Optional[Settings] = None
_auth_middleware: Optional[AuthMiddleware] = None
_gateway: Optional[AIGateway] = None
_cleanup_task: Optional[asyncio.Task] = None


async def cleanup_conversations_task(manager: ConversationManager, interval: int = 300):
    """Background task to clean up expired conversations."""
    while True:
        await asyncio.sleep(interval)
        try:
            await manager.cleanup_expired()
        except Exception as e:
            logger.error("Conversation cleanup failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _settings, _auth_middleware, _gateway, _cleanup_task
    
    # Startup
    logger.info("Starting Orchestrator")
    
    _settings = get_settings()
    setup_logging(_settings.log_level, json_output=_settings.environment == "production")
    
    # Initialize auth middleware
    _auth_middleware = AuthMiddleware(AuthConfig(
        secret_key=_settings.orchestrator.secret_key,
        token_expire_minutes=_settings.orchestrator.token_expire_minutes,
        trusted_clients=["frontend", "cli"],
        require_auth=_settings.mcp_server.require_auth,
    ))
    
    # Initialize LLM provider
    llm_provider = create_llm_provider(_settings.llm)
    
    # Initialize MCP client
    mcp_client = MCPClient(
        server_url=_settings.orchestrator.mcp_server_url,
        timeout=30.0
    )
    
    # Initialize conversation manager
    conversation_manager = ConversationManager(
        max_conversation_length=_settings.orchestrator.max_conversation_length,
        conversation_ttl_minutes=_settings.orchestrator.conversation_ttl_minutes
    )
    
    # Initialize gateway
    _gateway = AIGateway(
        llm_provider=llm_provider,
        mcp_client=mcp_client,
        conversation_manager=conversation_manager
    )
    
    # Start cleanup task
    _cleanup_task = asyncio.create_task(
        cleanup_conversations_task(conversation_manager)
    )
    
    logger.info("Orchestrator started", mcp_server=_settings.orchestrator.mcp_server_url)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Orchestrator")
    
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    
    await mcp_client.close()


# Create FastAPI app
app = FastAPI(
    title="MCP Orchestrator",
    description="AI Gateway for MCP-based execution platform",
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
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    status_info = await _gateway.health_check()
    
    return HealthResponse(
        status="healthy" if status_info.get("mcp_server") == "healthy" else "degraded",
        mcp_server=status_info.get("mcp_server", "unknown"),
        tool_count=status_info.get("tool_count", 0),
        conversation_count=status_info.get("conversations", {}).get("total_conversations", 0)
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    request: ChatRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Process a chat message.
    
    This is the main endpoint for the chat UI.
    """
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    try:
        result = await _gateway.process_message(
            user_message=request.message,
            user=user,
            conversation_id=request.conversation_id,
            allowed_domains=request.domains
        )
        
        return ChatResponse(
            conversation_id=result["conversation_id"],
            response=result["response"],
            request_id=result["request_id"]
        )
        
    except Exception as e:
        logger.error("Chat processing failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@app.get("/conversations", response_model=ConversationListResponse, tags=["Conversations"])
async def list_conversations(
    user: UserContext = Depends(get_current_user)
):
    """List user's conversations."""
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    conversations = await _gateway.conversations.list_conversations(user.user_id)
    return ConversationListResponse(conversations=conversations)


@app.get("/conversations/{conversation_id}", tags=["Conversations"])
async def get_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user)
):
    """Get conversation history."""
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    history = await _gateway.get_conversation_history(conversation_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return {"conversation_id": conversation_id, "messages": history}


@app.delete("/conversations/{conversation_id}", tags=["Conversations"])
async def delete_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user)
):
    """Delete a conversation."""
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    deleted = await _gateway.end_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return {"status": "deleted"}


@app.get("/tools", tags=["Tools"])
async def list_tools(
    domain: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """List available tools (proxy to MCP Server)."""
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway not initialized"
        )
    
    try:
        if domain:
            tools = await _gateway.tool_discovery.get_tools_by_domain(domain)
        else:
            tools = await _gateway.tool_discovery.get_all_tools()
        
        return {"tools": tools, "count": len(tools)}
        
    except Exception as e:
        logger.error("Failed to list tools", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve tools from MCP Server"
        )


def main():
    """Run the Orchestrator server."""
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "orchestrator.main:app",
        host=settings.orchestrator.host,
        port=settings.orchestrator.port,
        reload=settings.environment == "development"
    )


if __name__ == "__main__":
    main()
