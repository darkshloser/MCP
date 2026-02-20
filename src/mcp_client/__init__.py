"""MCP Client - Tool discovery and execution.

The MCP Client discovers tools from the MCP Server,
validates schemas, and executes tool calls.
It is stateless and reusable by UI, CLI, and services.
"""

from mcp_client.client import MCPClient
from mcp_client.discovery import ToolDiscovery

__all__ = [
    "MCPClient",
    "ToolDiscovery",
]
