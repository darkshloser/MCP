"""Base classes for domain adapters.

All adapters must:
- Translate MCP calls to APIs or CLI commands
- Handle authentication
- Normalize and filter responses
- Never make cross-domain calls
- Never have shared state
- Never depend on LLM
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from shared.logging import get_logger
from shared.models import (
    DomainConfig,
    ExecutionContext,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
)

logger = get_logger(__name__)


class BaseAdapter(ABC):
    """
    Base class for domain adapters.
    
    Each adapter:
    - Handles one domain only
    - Translates MCP calls to backend APIs
    - Is stateless
    - Has no LLM dependency
    """
    
    def __init__(self, config: DomainConfig) -> None:
        self.config = config
        self.domain = config.name
        self._tools: dict[str, ToolDefinition] = {}
    
    @property
    @abstractmethod
    def tools(self) -> list[ToolDefinition]:
        """Return all tool definitions for this domain."""
        pass
    
    @abstractmethod
    def execute(
        self,
        action: str,
        parameters: dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        Execute a tool action.
        
        Args:
            action: Action name (without domain prefix)
            parameters: Tool parameters
            context: Execution context with user info
        
        Returns:
            Tool execution result
        """
        pass
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name."""
        return self._tools.get(name)
    
    def _success(self, data: Any = None) -> ToolResult:
        """Create a success result."""
        return ToolResult(
            tool_name=f"{self.domain}.unknown",
            status=ToolResultStatus.SUCCESS,
            data=data
        )
    
    def _error(self, message: str, code: str = "ERROR") -> ToolResult:
        """Create an error result."""
        return ToolResult(
            tool_name=f"{self.domain}.unknown",
            status=ToolResultStatus.ERROR,
            error=message,
            error_code=code
        )
    
    def _not_found(self, action: str) -> ToolResult:
        """Create a not found result."""
        return ToolResult(
            tool_name=f"{self.domain}.{action}",
            status=ToolResultStatus.NOT_FOUND,
            error=f"Action '{action}' not found in domain '{self.domain}'",
            error_code="ACTION_NOT_FOUND"
        )


class RESTAdapter(BaseAdapter):
    """
    Base adapter for REST API backends.
    
    Provides common HTTP client functionality.
    """
    
    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self.base_url = config.base_url
        self.timeout = config.timeout_seconds
        self._client = None
    
    async def _get_client(self):
        """Get or create HTTP client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> dict[str, Any]:
        """Make an HTTP request to the backend."""
        client = await self._get_client()
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class CLIAdapter(BaseAdapter):
    """
    Base adapter for CLI-based backends.
    
    Translates tool calls to shell commands.
    """
    
    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self.command_prefix = config.base_url or ""  # Reuse base_url for command prefix
    
    async def _run_command(
        self,
        command: str,
        args: list[str],
        timeout: Optional[int] = None
    ) -> tuple[str, str, int]:
        """
        Run a CLI command.
        
        Args:
            command: Command to run
            args: Command arguments
            timeout: Optional timeout
        
        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        import asyncio
        
        timeout = timeout or self.config.timeout_seconds
        full_command = [command] + args
        
        if self.command_prefix:
            full_command = self.command_prefix.split() + full_command
        
        logger.debug("Running command", command=full_command)
        
        proc = await asyncio.create_subprocess_exec(
            *full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return (
                stdout.decode("utf-8"),
                stderr.decode("utf-8"),
                proc.returncode or 0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout}s")


class MockAdapter(BaseAdapter):
    """
    Mock adapter for testing.
    
    Returns predefined responses for tools.
    """
    
    def __init__(
        self,
        config: DomainConfig,
        tools: list[ToolDefinition],
        responses: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(config)
        self._tool_list = tools
        self._responses = responses or {}
        
        for tool in tools:
            self._tools[tool.name] = tool
    
    @property
    def tools(self) -> list[ToolDefinition]:
        return self._tool_list
    
    def set_response(self, action: str, response: Any) -> None:
        """Set response for an action."""
        self._responses[action] = response
    
    def execute(
        self,
        action: str,
        parameters: dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        if action in self._responses:
            return self._success(self._responses[action])
        return self._error(f"No mock response for action: {action}")
