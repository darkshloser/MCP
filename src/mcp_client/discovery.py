"""Tool Discovery for MCP Client.

Provides caching and filtering for tool discovery.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

from shared.logging import get_logger
from mcp_client.client import MCPClient

logger = get_logger(__name__)


class ToolDiscovery:
    """
    Cached tool discovery from MCP Server.
    
    Provides:
    - Cached tool listings
    - Filtering by domain, name, or tags
    - Automatic cache refresh
    """
    
    def __init__(
        self,
        client: MCPClient,
        cache_ttl_seconds: int = 300  # 5 minutes
    ) -> None:
        """
        Initialize tool discovery.
        
        Args:
            client: MCP Client instance
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.client = client
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        
        self._cache: dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_time is None:
            return False
        return datetime.utcnow() - self._cache_time < self.cache_ttl
    
    async def _refresh_cache(self) -> None:
        """Refresh the tool cache from MCP Server."""
        async with self._lock:
            # Double-check after acquiring lock
            if self._is_cache_valid():
                return
            
            logger.debug("Refreshing tool cache")
            
            try:
                tools = await self.client.list_tools()
                domains = await self.client.list_domains()
                
                self._cache = {
                    "tools": tools,
                    "domains": domains,
                    "by_domain": self._group_by_domain(tools),
                    "by_name": {t["function"]["name"]: t for t in tools}
                }
                self._cache_time = datetime.utcnow()
                
                logger.info(
                    "Tool cache refreshed",
                    tool_count=len(tools),
                    domain_count=len(domains)
                )
            except Exception as e:
                logger.error("Failed to refresh tool cache", error=str(e))
                raise
    
    def _group_by_domain(
        self,
        tools: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group tools by domain."""
        by_domain: dict[str, list[dict[str, Any]]] = {}
        
        for tool in tools:
            name = tool["function"]["name"]
            domain = name.split(".")[0] if "." in name else "default"
            
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(tool)
        
        return by_domain
    
    async def get_all_tools(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get all available tools.
        
        Args:
            force_refresh: Force cache refresh
        
        Returns:
            List of tool definitions
        """
        if force_refresh or not self._is_cache_valid():
            await self._refresh_cache()
        
        return self._cache.get("tools", [])
    
    async def get_tools_by_domain(
        self,
        domain: str,
        force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get tools for a specific domain.
        
        Args:
            domain: Domain name
            force_refresh: Force cache refresh
        
        Returns:
            List of tool definitions for the domain
        """
        if force_refresh or not self._is_cache_valid():
            await self._refresh_cache()
        
        by_domain = self._cache.get("by_domain", {})
        return by_domain.get(domain, [])
    
    async def get_tool_by_name(
        self,
        name: str,
        force_refresh: bool = False
    ) -> Optional[dict[str, Any]]:
        """
        Get a specific tool by name.
        
        Args:
            name: Fully-qualified tool name
            force_refresh: Force cache refresh
        
        Returns:
            Tool definition or None if not found
        """
        if force_refresh or not self._is_cache_valid():
            await self._refresh_cache()
        
        by_name = self._cache.get("by_name", {})
        return by_name.get(name)
    
    async def search_tools(
        self,
        query: str,
        domain: Optional[str] = None,
        force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Search tools by name or description.
        
        Args:
            query: Search query (case-insensitive)
            domain: Optional domain filter
            force_refresh: Force cache refresh
        
        Returns:
            List of matching tool definitions
        """
        if domain:
            tools = await self.get_tools_by_domain(domain, force_refresh)
        else:
            tools = await self.get_all_tools(force_refresh)
        
        query_lower = query.lower()
        results = []
        
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "").lower()
            description = func.get("description", "").lower()
            
            if query_lower in name or query_lower in description:
                results.append(tool)
        
        return results
    
    async def get_domains(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get all registered domains.
        
        Args:
            force_refresh: Force cache refresh
        
        Returns:
            List of domain info
        """
        if force_refresh or not self._is_cache_valid():
            await self._refresh_cache()
        
        return self._cache.get("domains", [])
    
    def invalidate_cache(self) -> None:
        """Invalidate the tool cache."""
        self._cache_time = None
        self._cache.clear()
        logger.debug("Tool cache invalidated")
