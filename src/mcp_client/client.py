"""MCP Client for tool discovery and execution.

Provides a clean interface for interacting with the MCP Server.
Handles authentication, request formatting, and error handling.
"""

import uuid
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.logging import get_logger
from shared.models import ToolResult, ToolResultStatus, UserContext

logger = get_logger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP Client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Connection to MCP Server failed."""
    pass


class MCPAuthError(MCPClientError):
    """Authentication failed."""
    pass


class MCPClient:
    """
    Client for interacting with the MCP Server.
    
    Provides methods for:
    - Discovering available tools
    - Executing tool calls
    - Managing authentication
    
    The client is stateless and reusable.
    """
    
    def __init__(
        self,
        server_url: str = "http://localhost:8001",
        timeout: float = 30.0,
        auth_token: Optional[str] = None
    ) -> None:
        """
        Initialize MCP Client.
        
        Args:
            server_url: MCP Server base URL
            timeout: Request timeout in seconds
            auth_token: Optional authentication token
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._auth_token = auth_token
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def auth_token(self) -> Optional[str]:
        """Get current authentication token."""
        return self._auth_token
    
    @auth_token.setter
    def auth_token(self, token: Optional[str]) -> None:
        """Set authentication token."""
        self._auth_token = token
    
    def _get_headers(self) -> dict[str, str]:
        """Get request headers including authentication."""
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=self.timeout,
                headers=self._get_headers()
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def health_check(self) -> dict[str, Any]:
        """
        Check MCP Server health.
        
        Returns:
            Health status including available domains and tool count
        
        Raises:
            MCPConnectionError: If server is unreachable
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Cannot connect to MCP Server: {e}")
        except httpx.HTTPStatusError as e:
            raise MCPClientError(f"Health check failed: {e}")
    
    async def list_tools(
        self,
        domain: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        List available tools from MCP Server.
        
        Args:
            domain: Optional domain filter
        
        Returns:
            List of tool definitions in LLM-compatible format
        
        Raises:
            MCPConnectionError: If server is unreachable
            MCPAuthError: If authentication fails
        """
        try:
            client = await self._get_client()
            params = {"domain": domain} if domain else {}
            response = await client.get("/tools", params=params)
            
            if response.status_code == 401:
                raise MCPAuthError("Authentication required")
            if response.status_code == 403:
                raise MCPAuthError("Access denied")
            
            response.raise_for_status()
            data = response.json()
            return data.get("tools", [])
            
        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Cannot connect to MCP Server: {e}")
    
    async def get_tool(self, tool_name: str) -> Optional[dict[str, Any]]:
        """
        Get details for a specific tool.
        
        Args:
            tool_name: Fully-qualified tool name
        
        Returns:
            Tool definition or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/tools/{tool_name}")
            
            if response.status_code == 404:
                return None
            if response.status_code == 401:
                raise MCPAuthError("Authentication required")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Cannot connect to MCP Server: {e}")
    
    async def list_domains(self) -> list[dict[str, Any]]:
        """
        List all registered domains.
        
        Returns:
            List of domain info with tool counts
        """
        try:
            client = await self._get_client()
            response = await client.get("/domains")
            
            if response.status_code == 401:
                raise MCPAuthError("Authentication required")
            
            response.raise_for_status()
            data = response.json()
            return data.get("domains", [])
            
        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Cannot connect to MCP Server: {e}")
    
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        reraise=True
    )
    async def execute(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> ToolResult:
        """
        Execute a tool via the MCP Server.
        
        Args:
            tool_name: Fully-qualified tool name
            parameters: Tool parameters
            request_id: Optional request ID for tracing
            correlation_id: Optional correlation ID for tracing
        
        Returns:
            Tool execution result
        
        Raises:
            MCPConnectionError: If server is unreachable
            MCPAuthError: If authentication fails
        """
        request_id = request_id or str(uuid.uuid4())
        
        logger.debug(
            "Executing tool",
            tool=tool_name,
            request_id=request_id
        )
        
        try:
            client = await self._get_client()
            response = await client.post(
                "/execute",
                json={
                    "tool_name": tool_name,
                    "parameters": parameters,
                    "request_id": request_id,
                    "correlation_id": correlation_id
                }
            )
            
            if response.status_code == 401:
                raise MCPAuthError("Authentication required")
            if response.status_code == 403:
                raise MCPAuthError("Access denied")
            
            response.raise_for_status()
            data = response.json()
            
            return ToolResult(
                tool_name=data["tool_name"],
                status=ToolResultStatus(data["status"]),
                data=data.get("data"),
                error=data.get("error"),
                error_code=data.get("error_code"),
                execution_time_ms=data.get("execution_time_ms", 0)
            )
            
        except httpx.ConnectError as e:
            logger.error("MCP Server connection failed", error=str(e))
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=f"Cannot connect to MCP Server: {e}",
                error_code="CONNECTION_ERROR"
            )
        except httpx.HTTPStatusError as e:
            logger.error("MCP Server request failed", error=str(e))
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=f"Request failed: {e}",
                error_code="REQUEST_ERROR"
            )
    
    async def execute_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        correlation_id: Optional[str] = None
    ) -> list[ToolResult]:
        """
        Execute multiple tools in sequence.
        
        Args:
            calls: List of (tool_name, parameters) tuples
            correlation_id: Shared correlation ID for all calls
        
        Returns:
            List of tool results in order
        """
        correlation_id = correlation_id or str(uuid.uuid4())
        results = []
        
        for tool_name, parameters in calls:
            result = await self.execute(
                tool_name=tool_name,
                parameters=parameters,
                correlation_id=correlation_id
            )
            results.append(result)
        
        return results
