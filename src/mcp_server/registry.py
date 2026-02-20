"""Tool Registry for MCP Server.

Manages registration, discovery, and lookup of tools from all domains.
Tools are loaded from domain configurations and registered at startup.
"""

from typing import Any, Optional

from shared.logging import get_logger
from shared.models import ToolDefinition, ToolResultStatus
from shared.schema import validate_schema

logger = get_logger(__name__)


class ToolRegistry:
    """
    Central registry for all MCP tools.
    
    Responsibilities:
    - Register tools from domains
    - Discover available tools
    - Lookup tools by name
    - Validate tool schemas
    """
    
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._domains: set[str] = set()
    
    def register(self, tool: ToolDefinition) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool definition to register
        
        Raises:
            ValueError: If tool name is already registered
        """
        qualified_name = tool.qualified_name
        
        if qualified_name in self._tools:
            raise ValueError(f"Tool '{qualified_name}' is already registered")
        
        self._tools[qualified_name] = tool
        self._domains.add(tool.domain)
        
        logger.info(
            "Tool registered",
            tool=qualified_name,
            domain=tool.domain,
            execution_type=tool.execution_type.value
        )
    
    def register_many(self, tools: list[ToolDefinition]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)
    
    def unregister(self, tool_name: str) -> bool:
        """
        Unregister a tool from the registry.
        
        Args:
            tool_name: Fully-qualified tool name
        
        Returns:
            True if tool was removed, False if not found
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info("Tool unregistered", tool=tool_name)
            return True
        return False
    
    def get(self, tool_name: str) -> Optional[ToolDefinition]:
        """
        Get a tool by its fully-qualified name.
        
        Args:
            tool_name: Fully-qualified tool name (domain.action)
        
        Returns:
            ToolDefinition if found, None otherwise
        """
        return self._tools.get(tool_name)
    
    def list_tools(
        self,
        domain: Optional[str] = None,
        include_deprecated: bool = False
    ) -> list[ToolDefinition]:
        """
        List all registered tools, optionally filtered by domain.
        
        Args:
            domain: Filter by domain name
            include_deprecated: Include deprecated tools
        
        Returns:
            List of tool definitions
        """
        tools = list(self._tools.values())
        
        if domain:
            tools = [t for t in tools if t.domain == domain]
        
        if not include_deprecated:
            tools = [t for t in tools if not t.deprecated]
        
        return tools
    
    def list_domains(self) -> list[str]:
        """List all registered domains."""
        return sorted(self._domains)
    
    def validate_input(
        self,
        tool_name: str,
        parameters: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Validate input parameters against tool's input schema.
        
        Args:
            tool_name: Fully-qualified tool name
            parameters: Input parameters to validate
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        tool = self.get(tool_name)
        if not tool:
            return False, [f"Tool '{tool_name}' not found"]
        
        if not tool.input_schema:
            return True, []
        
        return validate_schema(parameters, tool.input_schema)
    
    def get_tools_for_llm(
        self,
        domains: Optional[list[str]] = None,
        user_roles: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Get tool definitions formatted for LLM consumption.
        
        Args:
            domains: Filter by domains (None = all)
            user_roles: User's roles for permission filtering
        
        Returns:
            List of tool definitions in LLM-compatible format
        """
        tools = self.list_tools()
        
        if domains:
            tools = [t for t in tools if t.domain in domains]
        
        # Filter by permissions if user_roles provided
        if user_roles is not None:
            filtered_tools = []
            for tool in tools:
                # Public tools are always accessible
                if tool.permissions.level.value == "public":
                    filtered_tools.append(tool)
                    continue
                
                # Check role-based access
                if any(role in tool.permissions.roles for role in user_roles):
                    filtered_tools.append(tool)
                    continue
                
                # User-level tools are accessible to any authenticated user
                if tool.permissions.level.value == "user" and user_roles:
                    filtered_tools.append(tool)
            
            tools = filtered_tools
        
        # Format for LLM (OpenAI function calling format)
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.qualified_name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
            for tool in tools
        ]
    
    def get_tool_count(self) -> dict[str, int]:
        """Get count of tools per domain."""
        counts: dict[str, int] = {}
        for tool in self._tools.values():
            counts[tool.domain] = counts.get(tool.domain, 0) + 1
        return counts
    
    def clear(self) -> None:
        """Clear all registered tools. Use with caution."""
        self._tools.clear()
        self._domains.clear()
        logger.warning("Tool registry cleared")


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
