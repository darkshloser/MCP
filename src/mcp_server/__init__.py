"""MCP Server - Tool registry, authorization, and execution routing.

The MCP Server is the authoritative component for tool execution.
It registers tools, enforces authorization, routes calls to domains,
and audits all executions.
"""

from mcp_server.registry import ToolRegistry
from mcp_server.router import ToolRouter
from mcp_server.auth import AuthMiddleware, authorize_request
from mcp_server.audit import AuditLogger

__all__ = [
    "ToolRegistry",
    "ToolRouter",
    "AuthMiddleware",
    "authorize_request",
    "AuditLogger",
]
