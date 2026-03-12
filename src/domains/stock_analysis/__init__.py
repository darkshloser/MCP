"""Stock Analysis Domain - News scraping from stockanalysis.com.

Provides tools for:
- Fetching live stock news with ticker symbols
- Paginated access to cached news items

The LLM in the Orchestrator layer handles ticker extraction
and sentiment analysis from the raw news data returned here.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup

from shared.logging import get_logger
from shared.models import (
    DomainConfig,
    ExecutionContext,
    ExecutionType,
    Permission,
    PermissionLevel,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
)
from domains.base import BaseAdapter

logger = get_logger(__name__)

NEWS_URL = "https://stockanalysis.com/news/all-stocks/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class StockAnalysisAdapter(BaseAdapter):
    """
    Stock Analysis Domain Adapter.

    Scrapes live stock news from stockanalysis.com and returns
    structured news items with headline, summary, ticker symbols,
    and source URL.

    The LLM (in the Orchestrator) is responsible for:
    - Sentiment analysis (Positive / Negative)
    - Formatting the final output

    This adapter performs no LLM calls — it only fetches and
    parses HTML.
    """

    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self._cache: dict[str, Any] = {}
        self._cache_ttl = timedelta(
            seconds=config.features.get("cache_ttl_seconds", 300)
        )
        self._max_items: int = config.features.get("max_items", 50)
        self._define_tools()

    def _define_tools(self) -> None:
        """Define all Stock Analysis tools."""

        # stock_analysis.scrape_news
        self._tools["scrape_news"] = ToolDefinition(
            name="scrape_news",
            domain="stock_analysis",
            description=(
                "Fetch the latest stock market news from stockanalysis.com. "
                "Returns a list of news items, each containing the headline, "
                "a short summary, the stock ticker symbols mentioned (e.g. LYV, "
                "AMZN, PDD), and the article URL. "
                "Use this tool when the user asks about stock news, market news, "
                "or wants to know which stocks are in the news today."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of news items to return (default: 20, max: 50)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "force_refresh": {
                        "type": "boolean",
                        "description": "Bypass the 5-minute cache and fetch fresh data (default: false)",
                        "default": False,
                    },
                },
                "required": [],
            },
            output_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "summary": {"type": "string"},
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Stock ticker symbols mentioned in this article",
                        },
                        "url": {"type": "string"},
                        "scraped_at": {"type": "string"},
                    },
                },
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER),
            examples=[
                {
                    "input": {"limit": 10},
                    "description": "Get 10 latest stock news items",
                }
            ],
        )

        # stock_analysis.get_news
        self._tools["get_news"] = ToolDefinition(
            name="get_news",
            domain="stock_analysis",
            description=(
                "Get a paginated slice of the cached stock news. "
                "Use after scrape_news has already been called, or when you need "
                "a specific subset of items (e.g. items 10-20). "
                "Automatically triggers a scrape if the cache is empty or expired."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of items to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of items to skip from the start (default: 0)",
                        "default": 0,
                        "minimum": 0,
                    },
                },
                "required": [],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "total": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "scraped_at": {"type": "string"},
                },
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER),
        )

    @property
    def tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def execute(
        self,
        action: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute a Stock Analysis action."""
        logger.debug(
            "Stock Analysis action",
            action=action,
            user=context.user.user_id,
        )

        handlers = {
            "scrape_news": self._scrape_news,
            "get_news": self._get_news,
        }

        handler = handlers.get(action)
        if not handler:
            return self._not_found(action)

        try:
            return await handler(parameters, context)
        except httpx.TimeoutException:
            logger.warning("Scrape timed out", action=action)
            return ToolResult(
                tool_name=f"stock_analysis.{action}",
                status=ToolResultStatus.ERROR,
                error="Request to stockanalysis.com timed out. Please try again.",
                error_code="TIMEOUT",
            )
        except httpx.HTTPStatusError as e:
            logger.warning("Scrape HTTP error", action=action, status=e.response.status_code)
            return ToolResult(
                tool_name=f"stock_analysis.{action}",
                status=ToolResultStatus.ERROR,
                error=f"stockanalysis.com returned HTTP {e.response.status_code}",
                error_code="HTTP_ERROR",
            )
        except Exception as e:
            logger.error("Stock Analysis action failed", action=action, error=str(e))
            return ToolResult(
                tool_name=f"stock_analysis.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="EXECUTION_ERROR",
            )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _scrape_news(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        limit = min(int(params.get("limit", 20)), self._max_items)
        force_refresh = bool(params.get("force_refresh", False))

        news_items = await self._get_cached_or_fetch(force_refresh)

        if not news_items:
            return ToolResult(
                tool_name="stock_analysis.scrape_news",
                status=ToolResultStatus.ERROR,
                error=(
                    "Scraping returned 0 news items. "
                    "The page structure may have changed or the site may require "
                    "JavaScript rendering."
                ),
                error_code="SCRAPE_EMPTY",
            )

        return ToolResult(
            tool_name="stock_analysis.scrape_news",
            status=ToolResultStatus.SUCCESS,
            data=news_items[:limit],
        )

    async def _get_news(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        limit = min(int(params.get("limit", 10)), self._max_items)
        offset = max(int(params.get("offset", 0)), 0)

        news_items = await self._get_cached_or_fetch(force_refresh=False)

        scraped_at = self._cache.get("scraped_at", "")
        page = news_items[offset: offset + limit]

        return ToolResult(
            tool_name="stock_analysis.get_news",
            status=ToolResultStatus.SUCCESS,
            data={
                "items": page,
                "total": len(news_items),
                "offset": offset,
                "scraped_at": scraped_at,
            },
        )

    # ------------------------------------------------------------------
    # Scraping helpers
    # ------------------------------------------------------------------

    def _is_cache_valid(self) -> bool:
        if "news" not in self._cache or "cached_at" not in self._cache:
            return False
        age = datetime.utcnow() - self._cache["cached_at"]
        return age < self._cache_ttl

    async def _get_cached_or_fetch(self, force_refresh: bool) -> list[dict[str, Any]]:
        if not force_refresh and self._is_cache_valid():
            logger.debug("Returning cached news", count=len(self._cache["news"]))
            return self._cache["news"]

        logger.info("Fetching fresh news from stockanalysis.com")
        html = await self._fetch_page()
        items = self._parse_news_items(html)

        now = datetime.utcnow()
        self._cache = {
            "news": items,
            "cached_at": now,
            "scraped_at": now.isoformat() + "Z",
        }
        logger.info("News cache updated", count=len(items))
        return items

    async def _fetch_page(self) -> str:
        timeout = self.config.timeout_seconds or 30
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                NEWS_URL,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.text

    def _parse_news_items(self, html: str) -> list[dict[str, Any]]:
        """Parse news items from stockanalysis.com HTML."""
        soup = BeautifulSoup(html, "lxml")
        scraped_at = datetime.utcnow().isoformat() + "Z"
        items: list[dict[str, Any]] = []

        # stockanalysis.com renders news as <a> links inside a news list.
        # Each article link contains the headline; sibling/child elements
        # contain the summary and stock symbols.
        # We look for elements that contain "Stocks:" text to locate articles.
        for article in soup.find_all("div", recursive=True):
            # Look for blocks that have a stocks label
            stocks_label = article.find(
                lambda tag: tag.name in ("div", "span", "p")
                and tag.get_text(strip=True).startswith("Stocks:")
            )
            if not stocks_label:
                continue

            # Extract tickers from the "Stocks: LYV AMZN PDD" text
            stocks_text = stocks_label.get_text(strip=True)
            tickers = _extract_tickers(stocks_text)
            if not tickers:
                continue

            # Headline: first <a> or <h2>/<h3> in the block
            headline_tag = article.find(["h2", "h3", "a"])
            headline = headline_tag.get_text(strip=True) if headline_tag else ""

            # URL: from the <a> tag
            url = ""
            link_tag = article.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                url = href if href.startswith("http") else f"https://stockanalysis.com{href}"

            # Summary: first <p> that is not the stocks label
            summary = ""
            for p in article.find_all("p"):
                text = p.get_text(strip=True)
                if text and not text.startswith("Stocks:"):
                    summary = text
                    break

            if headline:
                items.append(
                    {
                        "headline": headline,
                        "summary": summary,
                        "tickers": tickers,
                        "url": url,
                        "scraped_at": scraped_at,
                    }
                )

            if len(items) >= self._max_items:
                break

        return items


def _extract_tickers(stocks_text: str) -> list[str]:
    """Extract ticker symbols from a 'Stocks: LYV AMZN PDD' string."""
    # Remove the "Stocks:" prefix and split on whitespace/commas
    text = stocks_text.replace("Stocks:", "").strip()
    # Tickers are uppercase letters (1-5 chars), optionally separated by spaces or commas
    import re
    return re.findall(r"\b[A-Z]{1,5}\b", text)


def register_stock_analysis_domain(router) -> None:
    """Register the Stock Analysis domain with the MCP server."""
    config = DomainConfig(
        name="stock_analysis",
        description="Stock Analysis domain for live news scraping from stockanalysis.com",
        version="1.0.0",
        base_url="https://stockanalysis.com",
        timeout_seconds=120,
        features={
            "cache_ttl_seconds": 300,
            "max_items": 50,
        },
    )

    adapter = StockAnalysisAdapter(config)

    # Register tools
    from mcp_server.registry import get_registry
    registry = get_registry()
    registry.register_many(adapter.tools)

    # Register async adapter executor
    router.register_adapter("stock_analysis", adapter.execute)

    logger.info("Stock Analysis domain registered", tool_count=len(adapter.tools))
