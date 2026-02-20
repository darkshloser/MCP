"""LLM Integration Layer using LlamaIndex.

Supports multiple LLM providers via LlamaIndex-compatible packages:
- Azure OpenAI
- OpenAI
- Other LlamaIndex-supported providers

The LLM has no direct MCP or application access.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from shared.config import LLMSettings
from shared.logging import get_logger
from shared.models import ConversationMessage, LLMResponse

logger = get_logger(__name__)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    LLM Integration Rules:
    - LLM receives only allowed tools and context
    - LLM outputs either a structured tool call or a final user response
    - LLM must not access APIs directly or decide authorization
    """
    
    @abstractmethod
    async def complete(
        self,
        messages: list[ConversationMessage],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.
        
        Args:
            messages: Conversation history
            tools: Available tools in OpenAI function format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        
        Returns:
            LLM response with content and/or tool calls
        """
        pass
    
    @abstractmethod
    async def complete_with_structured_output(
        self,
        messages: list[ConversationMessage],
        output_schema: dict[str, Any],
        temperature: Optional[float] = None
    ) -> dict[str, Any]:
        """
        Generate a completion with structured output.
        
        Args:
            messages: Conversation history
            output_schema: JSON Schema for output
            temperature: Sampling temperature
        
        Returns:
            Structured output matching the schema
        """
        pass


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI LLM provider using LlamaIndex."""
    
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._llm = None
    
    def _get_llm(self):
        """Lazy initialization of LlamaIndex LLM."""
        if self._llm is None:
            from llama_index.llms.azure_openai import AzureOpenAI
            
            self._llm = AzureOpenAI(
                deployment_name=self.settings.deployment_name or self.settings.model,
                api_key=self.settings.api_key,
                azure_endpoint=self.settings.api_base,
                api_version=self.settings.api_version,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )
        return self._llm
    
    def _convert_messages(self, messages: list[ConversationMessage]) -> list[dict[str, Any]]:
        """Convert internal messages to LlamaIndex format."""
        from llama_index.core.llms import ChatMessage, MessageRole
        
        result = []
        for msg in messages:
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
                "tool": MessageRole.TOOL,
            }
            
            chat_msg = ChatMessage(
                role=role_map.get(msg.role, MessageRole.USER),
                content=msg.content,
            )
            
            # Add tool call information if present
            if msg.tool_calls:
                chat_msg.additional_kwargs = {"tool_calls": msg.tool_calls}
            if msg.tool_call_id:
                chat_msg.additional_kwargs = {"tool_call_id": msg.tool_call_id}
            
            result.append(chat_msg)
        
        return result
    
    async def complete(
        self,
        messages: list[ConversationMessage],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generate completion using Azure OpenAI."""
        llm = self._get_llm()
        chat_messages = self._convert_messages(messages)
        
        # Temporarily override settings if provided
        if temperature is not None:
            llm.temperature = temperature
        if max_tokens is not None:
            llm.max_tokens = max_tokens
        
        try:
            if tools:
                # Use function calling
                response = await llm.achat(
                    chat_messages,
                    tools=tools
                )
            else:
                response = await llm.achat(chat_messages)
            
            # Extract tool calls if present
            tool_calls = None
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response.tool_calls
                ]
            
            return LLMResponse(
                content=response.message.content if response.message else None,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage={}  # LlamaIndex may not provide usage info
            )
            
        except Exception as e:
            logger.error("LLM completion failed", error=str(e))
            raise
    
    async def complete_with_structured_output(
        self,
        messages: list[ConversationMessage],
        output_schema: dict[str, Any],
        temperature: Optional[float] = None
    ) -> dict[str, Any]:
        """Generate structured output."""
        llm = self._get_llm()
        chat_messages = self._convert_messages(messages)
        
        if temperature is not None:
            llm.temperature = temperature
        
        # Use JSON mode or structured output
        try:
            # Add instruction to output JSON
            system_msg = ConversationMessage(
                role="system",
                content=f"You must respond with valid JSON matching this schema: {json.dumps(output_schema)}"
            )
            all_messages = [system_msg] + messages
            chat_messages = self._convert_messages(all_messages)
            
            response = await llm.achat(chat_messages)
            content = response.message.content if response.message else "{}"
            
            # Parse JSON response
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse structured output", error=str(e))
            raise ValueError(f"Invalid JSON response: {e}")


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider using LlamaIndex."""
    
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._llm = None
    
    def _get_llm(self):
        """Lazy initialization of LlamaIndex LLM."""
        if self._llm is None:
            from llama_index.llms.openai import OpenAI
            
            self._llm = OpenAI(
                model=self.settings.model,
                api_key=self.settings.api_key,
                api_base=self.settings.api_base,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )
        return self._llm
    
    def _convert_messages(self, messages: list[ConversationMessage]) -> list:
        """Convert internal messages to LlamaIndex format."""
        from llama_index.core.llms import ChatMessage, MessageRole
        
        result = []
        for msg in messages:
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
                "tool": MessageRole.TOOL,
            }
            
            chat_msg = ChatMessage(
                role=role_map.get(msg.role, MessageRole.USER),
                content=msg.content,
            )
            
            if msg.tool_calls:
                chat_msg.additional_kwargs = {"tool_calls": msg.tool_calls}
            if msg.tool_call_id:
                chat_msg.additional_kwargs = {"tool_call_id": msg.tool_call_id}
            
            result.append(chat_msg)
        
        return result
    
    async def complete(
        self,
        messages: list[ConversationMessage],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generate completion using OpenAI."""
        llm = self._get_llm()
        chat_messages = self._convert_messages(messages)
        
        if temperature is not None:
            llm.temperature = temperature
        if max_tokens is not None:
            llm.max_tokens = max_tokens
        
        try:
            if tools:
                response = await llm.achat(chat_messages, tools=tools)
            else:
                response = await llm.achat(chat_messages)
            
            tool_calls = None
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response.tool_calls
                ]
            
            return LLMResponse(
                content=response.message.content if response.message else None,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage={}
            )
            
        except Exception as e:
            logger.error("LLM completion failed", error=str(e))
            raise
    
    async def complete_with_structured_output(
        self,
        messages: list[ConversationMessage],
        output_schema: dict[str, Any],
        temperature: Optional[float] = None
    ) -> dict[str, Any]:
        """Generate structured output."""
        llm = self._get_llm()
        chat_messages = self._convert_messages(messages)
        
        if temperature is not None:
            llm.temperature = temperature
        
        try:
            system_msg = ConversationMessage(
                role="system",
                content=f"Respond with valid JSON matching: {json.dumps(output_schema)}"
            )
            all_messages = [system_msg] + messages
            chat_messages = self._convert_messages(all_messages)
            
            response = await llm.achat(chat_messages)
            content = response.message.content if response.message else "{}"
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse structured output", error=str(e))
            raise ValueError(f"Invalid JSON response: {e}")


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing without API calls."""
    
    def __init__(self, settings: Optional[LLMSettings] = None) -> None:
        self.settings = settings
        self.call_history: list[dict[str, Any]] = []
        self._next_response: Optional[LLMResponse] = None
    
    def set_next_response(self, response: LLMResponse) -> None:
        """Set the next response to return."""
        self._next_response = response
    
    async def complete(
        self,
        messages: list[ConversationMessage],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Return mock response."""
        self.call_history.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens
        })
        
        if self._next_response:
            response = self._next_response
            self._next_response = None
            return response
        
        # Default mock response
        return LLMResponse(
            content="This is a mock response.",
            tool_calls=None,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5}
        )
    
    async def complete_with_structured_output(
        self,
        messages: list[ConversationMessage],
        output_schema: dict[str, Any],
        temperature: Optional[float] = None
    ) -> dict[str, Any]:
        """Return mock structured output."""
        return {"result": "mock"}


def create_llm_provider(settings: LLMSettings) -> LLMProvider:
    """
    Factory function to create appropriate LLM provider.
    
    Supports:
    - azure_openai: Azure OpenAI Service
    - openai: OpenAI API
    - mock: Mock provider for testing
    
    Args:
        settings: LLM configuration settings
    
    Returns:
        Configured LLM provider
    
    Raises:
        ValueError: If provider is not supported
    """
    providers = {
        "azure_openai": AzureOpenAIProvider,
        "openai": OpenAIProvider,
        "mock": MockLLMProvider,
    }
    
    provider_class = providers.get(settings.provider)
    if not provider_class:
        raise ValueError(
            f"Unsupported LLM provider: {settings.provider}. "
            f"Supported: {list(providers.keys())}"
        )
    
    logger.info("Creating LLM provider", provider=settings.provider, model=settings.model)
    return provider_class(settings)
