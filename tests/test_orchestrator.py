"""Tests for orchestrator components."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.models import (
    ConversationMessage,
    LLMResponse,
    ToolResult,
    ToolResultStatus,
    UserContext,
)


class TestConversationManager:
    """Tests for ConversationManager."""
    
    @pytest.mark.asyncio
    async def test_create_conversation(self):
        """Test creating a new conversation."""
        from orchestrator.conversation import ConversationManager
        
        manager = ConversationManager()
        user = UserContext(user_id="user1", username="test")
        
        conversation = await manager.create(user, system_prompt="You are helpful.")
        
        assert conversation.id is not None
        assert conversation.user.user_id == "user1"
        assert len(conversation.messages) == 1
        assert conversation.messages[0].role == "system"
    
    @pytest.mark.asyncio
    async def test_add_messages(self):
        """Test adding messages to conversation."""
        from orchestrator.conversation import ConversationManager
        
        manager = ConversationManager()
        user = UserContext(user_id="user1", username="test")
        
        conversation = await manager.create(user)
        
        await manager.add_user_message(conversation.id, "Hello")
        await manager.add_assistant_message(conversation.id, "Hi there!")
        
        messages = await manager.get_messages(conversation.id, include_system=False)
        
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].role == "assistant"
    
    @pytest.mark.asyncio
    async def test_conversation_expiry(self):
        """Test that expired conversations return None."""
        from orchestrator.conversation import ConversationManager
        from datetime import datetime, timedelta
        
        manager = ConversationManager(conversation_ttl_minutes=0)  # Immediate expiry
        user = UserContext(user_id="user1", username="test")
        
        conversation = await manager.create(user)
        # Manually expire by setting old timestamp
        conversation.updated_at = datetime.utcnow() - timedelta(minutes=5)
        
        result = await manager.get(conversation.id)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_message_limit(self):
        """Test that messages are pruned when over limit."""
        from orchestrator.conversation import ConversationManager
        
        manager = ConversationManager(max_conversation_length=5)
        user = UserContext(user_id="user1", username="test")
        
        conversation = await manager.create(user, system_prompt="System")
        
        # Add more messages than limit
        for i in range(10):
            await manager.add_user_message(conversation.id, f"Message {i}")
        
        messages = await manager.get_messages(conversation.id)
        
        # Should keep system message + most recent messages up to limit
        assert len(messages) <= 5


class TestLLMProvider:
    """Tests for LLM providers."""
    
    @pytest.mark.asyncio
    async def test_mock_provider(self):
        """Test mock LLM provider."""
        from orchestrator.llm import MockLLMProvider
        
        provider = MockLLMProvider()
        messages = [ConversationMessage(role="user", content="Hello")]
        
        response = await provider.complete(messages)
        
        assert response.content is not None
        assert response.finish_reason == "stop"
    
    @pytest.mark.asyncio
    async def test_mock_provider_with_preset_response(self):
        """Test mock provider with preset response."""
        from orchestrator.llm import MockLLMProvider
        
        provider = MockLLMProvider()
        provider.set_next_response(LLMResponse(
            content="Custom response",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "test.action", "arguments": "{}"}
            }],
            finish_reason="tool_calls"
        ))
        
        messages = [ConversationMessage(role="user", content="Use a tool")]
        response = await provider.complete(messages)
        
        assert response.content == "Custom response"
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
    
    def test_create_llm_provider_factory(self):
        """Test LLM provider factory."""
        from orchestrator.llm import create_llm_provider
        from shared.config import LLMSettings
        
        settings = LLMSettings(provider="mock")
        provider = create_llm_provider(settings)
        
        assert provider is not None
    
    def test_invalid_provider_raises(self):
        """Test that invalid provider raises error."""
        from orchestrator.llm import create_llm_provider
        from shared.config import LLMSettings
        
        settings = LLMSettings(provider="invalid_provider")
        
        with pytest.raises(ValueError, match="Unsupported"):
            create_llm_provider(settings)


class TestAIGateway:
    """Tests for AI Gateway."""
    
    @pytest.mark.asyncio
    async def test_process_message_simple(self):
        """Test processing a simple message without tools."""
        from orchestrator.gateway import AIGateway
        from orchestrator.llm import MockLLMProvider
        from mcp_client.client import MCPClient
        
        llm = MockLLMProvider()
        llm.set_next_response(LLMResponse(
            content="Hello! How can I help you?",
            finish_reason="stop"
        ))
        
        mcp_client = MagicMock(spec=MCPClient)
        mcp_client.list_tools = AsyncMock(return_value=[])
        
        gateway = AIGateway(
            llm_provider=llm,
            mcp_client=mcp_client
        )
        
        user = UserContext(user_id="user1", username="test")
        result = await gateway.process_message("Hello", user)
        
        assert "conversation_id" in result
        assert "response" in result
        assert result["response"] == "Hello! How can I help you?"
    
    @pytest.mark.asyncio
    async def test_process_message_with_tool_call(self):
        """Test processing message that triggers tool use."""
        from orchestrator.gateway import AIGateway
        from orchestrator.llm import MockLLMProvider
        from mcp_client.client import MCPClient
        
        llm = MockLLMProvider()
        
        # First call returns tool call
        llm.set_next_response(LLMResponse(
            content="Let me look that up.",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "hr.get_employee",
                    "arguments": '{"employee_id": "E001"}'
                }
            }],
            finish_reason="tool_calls"
        ))
        
        mcp_client = MagicMock(spec=MCPClient)
        mcp_client.list_tools = AsyncMock(return_value=[
            {
                "type": "function",
                "function": {
                    "name": "hr.get_employee",
                    "description": "Get employee",
                    "parameters": {}
                }
            }
        ])
        mcp_client.execute = AsyncMock(return_value=ToolResult(
            tool_name="hr.get_employee",
            status=ToolResultStatus.SUCCESS,
            data={"name": "Alice", "department": "Engineering"}
        ))
        
        gateway = AIGateway(
            llm_provider=llm,
            mcp_client=mcp_client
        )
        
        # Override the second LLM call to return final response
        original_complete = llm.complete
        call_count = [0]
        
        async def patched_complete(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                return LLMResponse(
                    content="Alice works in Engineering.",
                    finish_reason="stop"
                )
            return await original_complete(*args, **kwargs)
        
        llm.complete = patched_complete
        
        user = UserContext(user_id="user1", username="test")
        result = await gateway.process_message("Who is E001?", user)
        
        assert "response" in result
        mcp_client.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_max_tool_iterations(self):
        """Test that tool iterations are limited."""
        from orchestrator.gateway import AIGateway
        from orchestrator.llm import MockLLMProvider
        from mcp_client.client import MCPClient
        
        llm = MockLLMProvider()
        
        # Always return tool calls (infinite loop scenario)
        async def always_tool_call(*args, **kwargs):
            return LLMResponse(
                content="",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "test.action", "arguments": "{}"}
                }],
                finish_reason="tool_calls"
            )
        
        llm.complete = always_tool_call
        
        mcp_client = MagicMock(spec=MCPClient)
        mcp_client.list_tools = AsyncMock(return_value=[
            {"type": "function", "function": {"name": "test.action", "description": "Test", "parameters": {}}}
        ])
        mcp_client.execute = AsyncMock(return_value=ToolResult(
            tool_name="test.action",
            status=ToolResultStatus.SUCCESS,
            data={}
        ))
        
        gateway = AIGateway(
            llm_provider=llm,
            mcp_client=mcp_client,
            max_tool_iterations=3
        )
        
        user = UserContext(user_id="user1", username="test")
        result = await gateway.process_message("Do something", user)
        
        # Should stop after max iterations
        assert "couldn't complete" in result["response"].lower() or "steps" in result["response"].lower()
        assert mcp_client.execute.call_count <= 3
