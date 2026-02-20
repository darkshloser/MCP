"""Application Domains.

Each domain contains:
- Tool definitions
- Adapter implementation
- Permission model
- Configuration

Domains are isolated by design with no cross-domain calls or shared state.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_server.router import AsyncToolRouter


def load_all_domains(router: "AsyncToolRouter") -> None:
    """
    Load and register all application domains.
    
    This is called at MCP Server startup to register all
    domain tools and adapters.
    """
    from domains.hr import register_hr_domain
    from domains.erp import register_erp_domain
    from domains.devops import register_devops_domain
    
    # Register each domain
    register_hr_domain(router)
    register_erp_domain(router)
    register_devops_domain(router)


__all__ = ["load_all_domains"]
