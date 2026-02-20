"""Authentication and Authorization for MCP Server.

Handles:
- Client authentication (trusting authenticated MCP clients)
- User authorization (enforcing permissions per tool)
- Security middleware for FastAPI
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from shared.logging import get_logger
from shared.models import (
    ExecutionContext,
    Permission,
    PermissionLevel,
    ToolDefinition,
    ToolResultStatus,
    UserContext,
)

logger = get_logger(__name__)

# Security configuration
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """Data extracted from JWT token."""
    user_id: str
    username: str
    email: Optional[str] = None
    roles: list[str] = []
    permissions: list[str] = []
    client_id: Optional[str] = None
    exp: Optional[datetime] = None


class AuthConfig(BaseModel):
    """Authentication configuration."""
    secret_key: str
    token_expire_minutes: int = 60
    trusted_clients: list[str] = ["orchestrator"]
    require_auth: bool = True


class AuthMiddleware:
    """
    Authentication middleware for MCP Server.
    
    Validates JWT tokens and extracts user context.
    Only trusts authenticated MCP clients (e.g., orchestrator).
    """
    
    def __init__(self, config: AuthConfig) -> None:
        self.config = config
    
    def create_token(self, user: UserContext, client_id: str = "orchestrator") -> str:
        """
        Create a JWT token for a user.
        
        Args:
            user: User context
            client_id: Client identifier (must be trusted)
        
        Returns:
            JWT token string
        """
        expire = datetime.utcnow() + timedelta(minutes=self.config.token_expire_minutes)
        
        payload = {
            "sub": user.user_id,
            "username": user.username,
            "email": user.email,
            "roles": user.roles,
            "permissions": user.permissions,
            "client_id": client_id,
            "exp": expire,
        }
        
        return jwt.encode(payload, self.config.secret_key, algorithm=ALGORITHM)
    
    def verify_token(self, token: str) -> TokenData:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            Decoded token data
        
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.config.secret_key, algorithms=[ALGORITHM])
            
            token_data = TokenData(
                user_id=payload.get("sub", ""),
                username=payload.get("username", ""),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                client_id=payload.get("client_id"),
            )
            
            # Verify client is trusted
            if token_data.client_id not in self.config.trusted_clients:
                logger.warning(
                    "Untrusted client attempted access",
                    client_id=token_data.client_id
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Untrusted client"
                )
            
            return token_data
            
        except JWTError as e:
            logger.warning("Token verification failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def get_user_context(self, token_data: TokenData) -> UserContext:
        """Convert token data to user context."""
        return UserContext(
            user_id=token_data.user_id,
            username=token_data.username,
            email=token_data.email,
            roles=token_data.roles,
            permissions=token_data.permissions,
        )
    
    async def __call__(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = None
    ) -> Optional[UserContext]:
        """
        FastAPI dependency for authentication.
        
        Can be used as a dependency in route handlers.
        """
        if not self.config.require_auth:
            # Return anonymous user context for development
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
        
        token_data = self.verify_token(credentials.credentials)
        return self.get_user_context(token_data)


def authorize_request(
    tool: ToolDefinition,
    user: UserContext,
    context: ExecutionContext
) -> tuple[bool, Optional[str]]:
    """
    Check if a user is authorized to execute a tool.
    
    Authorization is enforced in MCP Server, never decided by the LLM.
    
    Args:
        tool: Tool definition with permission requirements
        user: User context with roles and permissions
        context: Execution context
    
    Returns:
        Tuple of (is_authorized, error_message)
    """
    permission = tool.permissions
    
    # Public tools are always accessible
    if permission.level == PermissionLevel.PUBLIC:
        logger.debug(
            "Access granted (public tool)",
            tool=tool.qualified_name,
            user=user.user_id
        )
        return True, None
    
    # System tools require system-level access
    if permission.level == PermissionLevel.SYSTEM:
        if "system" not in user.roles:
            logger.warning(
                "Access denied (system tool)",
                tool=tool.qualified_name,
                user=user.user_id
            )
            return False, "System-level access required"
    
    # Admin tools require admin role
    if permission.level == PermissionLevel.ADMIN:
        if "admin" not in user.roles:
            logger.warning(
                "Access denied (admin tool)",
                tool=tool.qualified_name,
                user=user.user_id
            )
            return False, "Admin access required"
    
    # Check specific role requirements
    if permission.roles:
        if not any(role in user.roles for role in permission.roles):
            logger.warning(
                "Access denied (role mismatch)",
                tool=tool.qualified_name,
                user=user.user_id,
                required_roles=permission.roles,
                user_roles=user.roles
            )
            return False, f"Required roles: {', '.join(permission.roles)}"
    
    # Check specific scope requirements
    if permission.scopes:
        if not any(scope in user.permissions for scope in permission.scopes):
            logger.warning(
                "Access denied (scope mismatch)",
                tool=tool.qualified_name,
                user=user.user_id,
                required_scopes=permission.scopes
            )
            return False, f"Required scopes: {', '.join(permission.scopes)}"
    
    logger.debug(
        "Access granted",
        tool=tool.qualified_name,
        user=user.user_id
    )
    return True, None


def check_rate_limit(
    user: UserContext,
    tool: ToolDefinition,
    rate_limit_rpm: int = 60
) -> tuple[bool, Optional[str]]:
    """
    Check if user has exceeded rate limits.
    
    This is a placeholder - in production, use Redis or similar
    for distributed rate limiting.
    
    Args:
        user: User context
        tool: Tool being called
        rate_limit_rpm: Requests per minute limit
    
    Returns:
        Tuple of (is_allowed, error_message)
    """
    # TODO: Implement actual rate limiting with Redis
    # For now, always allow
    return True, None
