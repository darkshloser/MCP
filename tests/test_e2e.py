"""End-to-end tests for the tool calling chain.

Tests the full flow: AIGateway -> MCPClient -> MCP Server -> Domain Adapter -> back.
Uses the real MCP Server (via httpx test client) with mock LLM to verify the
complete tool calling chain works correctly.
"""

import pytest
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from shared.models import (
    LLMResponse,
    ToolResultStatus,
    UserContext,
)
from mcp_server.main import app as mcp_app
from mcp_server.registry import get_registry
from mcp_server.router import AsyncToolRouter
from mcp_server.audit import get_audit_logger
from mcp_server.auth import AuthConfig, AuthMiddleware
from domains import load_all_domains
from mcp_client.client import MCPClient
from orchestrator.gateway import AIGateway
from orchestrator.llm import MockLLMProvider


@pytest.fixture(autouse=True)
async def setup_mcp_server():
    """Initialize MCP Server state (domains, router, auth) before tests."""
    import mcp_server.main as mcp_main

    registry = get_registry()
    registry.clear()

    audit_logger = get_audit_logger(log_path="logs/test_audit.log", enabled=False)
    router = AsyncToolRouter(registry=registry, audit_logger=audit_logger)
    load_all_domains(router)

    mcp_main._settings = type("Settings", (), {
        "mcp_server": type("MCPServer", (), {
            "require_auth": False,
            "trusted_clients": ["orchestrator", "cli"],
            "enable_audit": False,
            "audit_log_path": "logs/test_audit.log",
        })(),
        "orchestrator": type("Orchestrator", (), {
            "secret_key": "test-secret",
            "token_expire_minutes": 60,
        })(),
        "log_level": "DEBUG",
        "environment": "test",
    })()

    mcp_main._auth_middleware = AuthMiddleware(AuthConfig(
        secret_key="test-secret",
        token_expire_minutes=60,
        trusted_clients=["orchestrator", "cli"],
        require_auth=False,
    ))
    mcp_main._router = router

    yield

    registry.clear()


@pytest.fixture
async def mcp_test_client():
    """Create httpx AsyncClient backed by the real MCP Server ASGI app."""
    transport = ASGITransport(app=mcp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_llm():
    """Create a MockLLMProvider with controllable responses."""
    return MockLLMProvider()


class TestERPListInvoicesE2E:
    """End-to-end test for the ERP 'list pending invoices' flow."""

    @pytest.mark.asyncio
    async def test_mcp_server_health(self, mcp_test_client):
        """Verify MCP Server starts and registers ERP tools."""
        response = await mcp_test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "erp" in data["domains"]

    @pytest.mark.asyncio
    async def test_mcp_server_lists_erp_tools(self, mcp_test_client):
        """Verify ERP tools are discoverable via the MCP Server API."""
        response = await mcp_test_client.get("/tools", params={"domain": "erp"})
        assert response.status_code == 200
        data = response.json()
        tool_names = [t["function"]["name"] for t in data["tools"]]
        assert "erp.list_invoices" in tool_names
        assert "erp.get_invoice" in tool_names

    @pytest.mark.asyncio
    async def test_mcp_server_execute_list_pending_invoices(self, mcp_test_client):
        """Verify MCP Server can execute erp.list_invoices with status=pending."""
        response = await mcp_test_client.post("/execute", json={
            "tool_name": "erp.list_invoices",
            "parameters": {"status": "pending"},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        invoices = data["data"]
        assert isinstance(invoices, list)
        assert len(invoices) >= 1
        assert all(inv["status"] == "pending" for inv in invoices)

    @pytest.mark.asyncio
    async def test_full_chain_list_pending_invoices(self, mcp_test_client, mock_llm):
        """Test the full chain: user message -> LLM tool call -> MCP execute -> response.

        Simulates the LLM deciding to call erp.list_invoices, executing it via the
        real MCP Server, and returning a final response with the results.
        """
        call_count = 0

        async def mock_complete(messages, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                return LLMResponse(
                    content="Let me check the pending invoices for you.",
                    tool_calls=[{
                        "id": "call_pending_invoices",
                        "type": "function",
                        "function": {
                            "name": "erp.list_invoices",
                            "arguments": '{"status": "pending"}'
                        }
                    }],
                    finish_reason="tool_calls"
                )
            else:
                return LLMResponse(
                    content="You have 1 pending invoice: INV-002 from Tech Solutions Inc for $8,500.00 USD, due 2026-02-28.",
                    finish_reason="stop"
                )

        mock_llm.complete = mock_complete

        # Create MCPClient and inject the ASGI-backed httpx client
        mcp_client = MCPClient(server_url="http://test")
        mcp_client._client = mcp_test_client

        gateway = AIGateway(
            llm_provider=mock_llm,
            mcp_client=mcp_client,
        )

        user = UserContext(user_id="test_user", username="tester", roles=["user"])
        result = await gateway.process_message(
            "List all pending invoices",
            user=user,
            allowed_domains=["erp"],
        )

        assert "conversation_id" in result
        assert "response" in result
        assert "INV-002" in result["response"]
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_full_chain_get_invoice_by_id(self, mcp_test_client, mock_llm):
        """Test the full chain for getting a specific invoice by ID."""
        call_count = 0

        async def mock_complete(messages, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                return LLMResponse(
                    content="Let me fetch that invoice.",
                    tool_calls=[{
                        "id": "call_get_invoice",
                        "type": "function",
                        "function": {
                            "name": "erp.get_invoice",
                            "arguments": '{"invoice_id": "INV-001"}'
                        }
                    }],
                    finish_reason="tool_calls"
                )
            else:
                return LLMResponse(
                    content="Invoice INV-001 is from Acme Corp for $15,000.00 and has been paid.",
                    finish_reason="stop"
                )

        mock_llm.complete = mock_complete

        mcp_client = MCPClient(server_url="http://test")
        mcp_client._client = mcp_test_client

        gateway = AIGateway(
            llm_provider=mock_llm,
            mcp_client=mcp_client,
        )

        user = UserContext(user_id="test_user", username="tester", roles=["user"])
        result = await gateway.process_message(
            "Show me invoice INV-001",
            user=user,
            allowed_domains=["erp"],
        )

        assert "INV-001" in result["response"]
        assert call_count == 2


class TestHRDomainE2E:
    """End-to-end test for HR domain tools through the MCP Server."""

    @pytest.mark.asyncio
    async def test_execute_get_employee(self, mcp_test_client):
        """Verify executing hr.get_employee through the MCP Server."""
        response = await mcp_test_client.post("/execute", json={
            "tool_name": "hr.get_employee",
            "parameters": {"employee_id": "E001"},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "Alice Johnson"

    @pytest.mark.asyncio
    async def test_execute_search_employees(self, mcp_test_client):
        """Verify executing hr.search_employees through the MCP Server."""
        response = await mcp_test_client.post("/execute", json={
            "tool_name": "hr.search_employees",
            "parameters": {"department": "Engineering"},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


class TestToolDiscoveryE2E:
    """End-to-end tests for tool discovery across all domains."""

    @pytest.mark.asyncio
    async def test_all_domains_registered(self, mcp_test_client):
        """Verify all three domains are registered."""
        response = await mcp_test_client.get("/domains")
        assert response.status_code == 200
        data = response.json()
        domain_names = [d["name"] for d in data["domains"]]
        assert "hr" in domain_names
        assert "erp" in domain_names
        assert "devops" in domain_names

    @pytest.mark.asyncio
    async def test_tool_count(self, mcp_test_client):
        """Verify expected number of tools are visible to a regular user.

        Total registered: HR(5) + ERP(6) + DevOps(6) = 17
        Admin-only tools filtered out for anonymous user: hr.update_employee,
        devops.scale_deployment, devops.restart_deployment = 3
        Visible to user: 17 - 3 = 14
        """
        response = await mcp_test_client.get("/tools")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 14
