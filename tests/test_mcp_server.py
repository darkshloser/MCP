"""Tests for MCP Server components."""

import pytest
from unittest.mock import Mock, AsyncMock
import uuid

from shared.models import (
    DomainConfig,
    ExecutionContext,
    ExecutionType,
    Permission,
    PermissionLevel,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
    UserContext,
)


class TestToolRegistry:
    """Tests for the ToolRegistry."""
    
    def test_register_tool(self):
        """Test registering a tool."""
        from mcp_server.registry import ToolRegistry
        
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_action",
            domain="test",
            description="A test tool"
        )
        
        registry.register(tool)
        
        assert registry.get("test.test_action") is not None
        assert "test" in registry.list_domains()
    
    def test_register_duplicate_tool_raises(self):
        """Test that registering duplicate tool raises error."""
        from mcp_server.registry import ToolRegistry
        
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_action",
            domain="test",
            description="A test tool"
        )
        
        registry.register(tool)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool)
    
    def test_list_tools_by_domain(self):
        """Test listing tools filtered by domain."""
        from mcp_server.registry import ToolRegistry
        
        registry = ToolRegistry()
        
        registry.register(ToolDefinition(name="action1", domain="domain1", description="Test"))
        registry.register(ToolDefinition(name="action2", domain="domain1", description="Test"))
        registry.register(ToolDefinition(name="action3", domain="domain2", description="Test"))
        
        domain1_tools = registry.list_tools(domain="domain1")
        assert len(domain1_tools) == 2
        
        domain2_tools = registry.list_tools(domain="domain2")
        assert len(domain2_tools) == 1
    
    def test_validate_input(self):
        """Test input validation against schema."""
        from mcp_server.registry import ToolRegistry
        
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_action",
            domain="test",
            description="Test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"}
                },
                "required": ["name"]
            }
        )
        registry.register(tool)
        
        # Valid input
        is_valid, errors = registry.validate_input(
            "test.test_action",
            {"name": "test", "count": 5}
        )
        assert is_valid
        assert len(errors) == 0
        
        # Missing required field
        is_valid, errors = registry.validate_input(
            "test.test_action",
            {"count": 5}
        )
        assert not is_valid
        assert len(errors) > 0
    
    def test_get_tools_for_llm(self):
        """Test getting tools in LLM format."""
        from mcp_server.registry import ToolRegistry
        
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="get_user",
            domain="hr",
            description="Get user information",
            input_schema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"]
            }
        ))
        
        tools = registry.get_tools_for_llm()
        
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "hr.get_user"
        assert "description" in tools[0]["function"]


class TestAuthorization:
    """Tests for authorization logic."""
    
    def test_public_tool_access(self):
        """Test that public tools are always accessible."""
        from mcp_server.auth import authorize_request
        
        tool = ToolDefinition(
            name="list_items",
            domain="test",
            description="List items",
            permissions=Permission(level=PermissionLevel.PUBLIC)
        )
        
        user = UserContext(user_id="user1", username="test", roles=[])
        context = ExecutionContext(request_id="req1", user=user)
        
        authorized, error = authorize_request(tool, user, context)
        assert authorized
        assert error is None
    
    def test_admin_tool_requires_admin_role(self):
        """Test that admin tools require admin role."""
        from mcp_server.auth import authorize_request
        
        tool = ToolDefinition(
            name="delete_all",
            domain="test",
            description="Delete all",
            permissions=Permission(level=PermissionLevel.ADMIN)
        )
        
        # Regular user
        user = UserContext(user_id="user1", username="test", roles=["user"])
        context = ExecutionContext(request_id="req1", user=user)
        
        authorized, error = authorize_request(tool, user, context)
        assert not authorized
        assert "Admin" in error
        
        # Admin user
        admin = UserContext(user_id="admin1", username="admin", roles=["admin"])
        context = ExecutionContext(request_id="req2", user=admin)
        
        authorized, error = authorize_request(tool, admin, context)
        assert authorized
    
    def test_role_based_access(self):
        """Test role-based access control."""
        from mcp_server.auth import authorize_request
        
        tool = ToolDefinition(
            name="view_finances",
            domain="erp",
            description="View finances",
            permissions=Permission(
                level=PermissionLevel.USER,
                roles=["finance", "accountant"]
            )
        )
        
        # User without required role
        user = UserContext(user_id="user1", username="dev", roles=["developer"])
        context = ExecutionContext(request_id="req1", user=user)
        
        authorized, error = authorize_request(tool, user, context)
        assert not authorized
        
        # User with required role
        finance_user = UserContext(
            user_id="user2",
            username="accountant",
            roles=["finance"]
        )
        context = ExecutionContext(request_id="req2", user=finance_user)
        
        authorized, error = authorize_request(tool, finance_user, context)
        assert authorized


class TestAuditLogger:
    """Tests for audit logging."""
    
    @pytest.mark.asyncio
    async def test_audit_entry_creation(self):
        """Test creating audit entries."""
        from mcp_server.audit import AuditLogger
        
        logger = AuditLogger(enabled=True)
        
        tool = ToolDefinition(
            name="test_action",
            domain="test",
            description="Test",
            execution_type=ExecutionType.READ
        )
        
        user = UserContext(user_id="user1", username="test")
        context = ExecutionContext(request_id="req1", user=user)
        call = ToolCall(
            tool_name="test.test_action",
            parameters={"key": "value"},
            context=context
        )
        
        result = ToolResult(
            tool_name="test.test_action",
            status=ToolResultStatus.SUCCESS,
            data={"result": "ok"},
            execution_time_ms=50.0
        )
        
        entry = logger.create_entry(tool, call, result)
        
        assert entry.user_id == "user1"
        assert entry.tool_name == "test.test_action"
        assert entry.status == ToolResultStatus.SUCCESS
        assert entry.execution_time_ms == 50.0
    
    @pytest.mark.asyncio
    async def test_sensitive_data_redaction(self):
        """Test that sensitive parameters are redacted."""
        from mcp_server.audit import AuditLogger
        
        logger = AuditLogger(enabled=True)
        
        tool = ToolDefinition(name="login", domain="auth", description="Login")
        user = UserContext(user_id="user1", username="test")
        context = ExecutionContext(request_id="req1", user=user)
        call = ToolCall(
            tool_name="auth.login",
            parameters={
                "username": "testuser",
                "password": "secret123",
                "api_key": "key123"
            },
            context=context
        )
        
        result = ToolResult(
            tool_name="auth.login",
            status=ToolResultStatus.SUCCESS
        )
        
        entry = logger.create_entry(tool, call, result)
        
        assert entry.parameters["username"] == "testuser"
        assert entry.parameters["password"] == "[REDACTED]"
        assert entry.parameters["api_key"] == "[REDACTED]"


class TestToolRouter:
    """Tests for the tool router."""
    
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test executing an unknown tool returns not found."""
        from mcp_server.router import AsyncToolRouter
        from mcp_server.registry import ToolRegistry
        from mcp_server.audit import AuditLogger
        
        registry = ToolRegistry()
        audit = AuditLogger(enabled=False)
        router = AsyncToolRouter(registry=registry, audit_logger=audit)
        
        user = UserContext(user_id="user1", username="test")
        context = ExecutionContext(request_id="req1", user=user)
        call = ToolCall(
            tool_name="unknown.tool",
            parameters={},
            context=context
        )
        
        result = await router.execute(call)
        
        assert result.status == ToolResultStatus.NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_execute_with_validation_error(self):
        """Test executing with invalid parameters."""
        from mcp_server.router import AsyncToolRouter
        from mcp_server.registry import ToolRegistry
        from mcp_server.audit import AuditLogger
        
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="test_action",
            domain="test",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {"required_field": {"type": "string"}},
                "required": ["required_field"]
            }
        ))
        
        audit = AuditLogger(enabled=False)
        router = AsyncToolRouter(registry=registry, audit_logger=audit)
        
        user = UserContext(user_id="user1", username="test")
        context = ExecutionContext(request_id="req1", user=user)
        call = ToolCall(
            tool_name="test.test_action",
            parameters={},  # Missing required field
            context=context
        )
        
        result = await router.execute(call)
        
        assert result.status == ToolResultStatus.VALIDATION_ERROR
