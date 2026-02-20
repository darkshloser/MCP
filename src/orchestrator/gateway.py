"""AI Gateway - Core orchestration logic.

The gateway coordinates:
- Conversation management
- LLM interactions
- Tool discovery and execution via MCP Client
- Response generation
"""

import json
import uuid
from typing import Any, Optional

from shared.config import Settings
from shared.logging import get_logger
from shared.models import (
    ConversationMessage,
    LLMResponse,
    ToolResult,
    ToolResultStatus,
    UserContext,
)
from mcp_client.client import MCPClient
from mcp_client.discovery import ToolDiscovery
from orchestrator.llm import LLMProvider
from orchestrator.conversation import ConversationManager

logger = get_logger(__name__)


# Default system prompt
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant that can use tools to help users accomplish tasks.

When you need to perform an action, use the available tools. Each tool has a specific purpose described in its definition.

Guidelines:
- Always explain what you're doing before using a tool
- If a tool returns an error, explain the issue to the user
- If you're unsure which tool to use, ask the user for clarification
- Never make up information - use tools to get accurate data
"""


class AIGateway:
    """
    AI Gateway - Orchestrates LLM and MCP interactions.
    
    This is the central component that:
    1. Manages conversation state
    2. Interfaces with LLM via LlamaIndex
    3. Supplies tool definitions to LLM
    4. Parses structured tool calls
    5. Invokes MCP Client for tool execution
    6. Propagates authenticated user context
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_client: MCPClient,
        conversation_manager: Optional[ConversationManager] = None,
        system_prompt: Optional[str] = None,
        max_tool_iterations: int = 10
    ) -> None:
        """
        Initialize AI Gateway.
        
        Args:
            llm_provider: LLM provider for completions
            mcp_client: MCP client for tool execution
            conversation_manager: Optional conversation manager
            system_prompt: Custom system prompt
            max_tool_iterations: Maximum tool call iterations per request
        """
        self.llm = llm_provider
        self.mcp_client = mcp_client
        self.conversations = conversation_manager or ConversationManager()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tool_iterations = max_tool_iterations
        
        # Tool discovery with caching
        self.tool_discovery = ToolDiscovery(mcp_client)
    
    async def process_message(
        self,
        user_message: str,
        user: UserContext,
        conversation_id: Optional[str] = None,
        allowed_domains: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        Process a user message and generate a response.
        
        This is the main entry point for chat interactions.
        
        Args:
            user_message: User's input message
            user: Authenticated user context
            conversation_id: Optional existing conversation ID
            allowed_domains: Optional domain filter for tools
        
        Returns:
            Response containing assistant message and metadata
        """
        request_id = str(uuid.uuid4())
        logger.info(
            "Processing message",
            request_id=request_id,
            user=user.user_id,
            conversation_id=conversation_id
        )
        
        # Get or create conversation
        conversation = await self.conversations.get_or_create(
            conversation_id=conversation_id,
            user=user,
            system_prompt=self.system_prompt
        )
        
        # Add user message
        await self.conversations.add_user_message(conversation.id, user_message)
        
        # Get available tools
        tools = await self._get_tools_for_user(user, allowed_domains)
        
        # Process with LLM (may involve multiple tool calls)
        final_response = await self._process_with_tools(
            conversation.id,
            tools,
            request_id
        )
        
        # Add assistant response
        await self.conversations.add_assistant_message(
            conversation.id,
            final_response
        )
        
        return {
            "conversation_id": conversation.id,
            "response": final_response,
            "request_id": request_id
        }
    
    async def _get_tools_for_user(
        self,
        user: UserContext,
        allowed_domains: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """Get tools available to the user."""
        try:
            all_tools = await self.tool_discovery.get_all_tools()
            
            # Filter by domain if specified
            if allowed_domains:
                filtered = []
                for tool in all_tools:
                    name = tool.get("function", {}).get("name", "")
                    domain = name.split(".")[0] if "." in name else "default"
                    if domain in allowed_domains:
                        filtered.append(tool)
                return filtered
            
            return all_tools
            
        except Exception as e:
            logger.warning("Failed to get tools", error=str(e))
            return []
    
    async def _process_with_tools(
        self,
        conversation_id: str,
        tools: list[dict[str, Any]],
        request_id: str
    ) -> str:
        """
        Process conversation with potential tool calls.
        
        Implements the tool calling loop:
        1. Call LLM with messages and tools
        2. If LLM requests tool calls, execute them
        3. Add tool results to conversation
        4. Repeat until LLM returns final response
        """
        iterations = 0
        
        while iterations < self.max_tool_iterations:
            iterations += 1
            
            # Get conversation messages
            messages = await self.conversations.get_messages(conversation_id)
            
            # Call LLM
            llm_response = await self.llm.complete(
                messages=messages,
                tools=tools if tools else None
            )
            
            # Check if LLM wants to use tools
            if llm_response.tool_calls:
                logger.debug(
                    "LLM requested tool calls",
                    count=len(llm_response.tool_calls),
                    iteration=iterations
                )
                
                # Add assistant message with tool calls
                await self.conversations.add_assistant_message(
                    conversation_id,
                    llm_response.content or "",
                    tool_calls=llm_response.tool_calls
                )
                
                # Execute each tool call
                for tool_call in llm_response.tool_calls:
                    result = await self._execute_tool_call(tool_call, request_id)
                    
                    # Add tool result to conversation
                    await self.conversations.add_tool_result(
                        conversation_id,
                        tool_call["id"],
                        self._format_tool_result(result)
                    )
            else:
                # LLM returned final response
                return llm_response.content or "I apologize, but I couldn't generate a response."
        
        # Max iterations reached
        logger.warning(
            "Max tool iterations reached",
            conversation_id=conversation_id,
            iterations=iterations
        )
        return "I apologize, but I wasn't able to complete the task within the allowed number of steps."
    
    async def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
        request_id: str
    ) -> ToolResult:
        """Execute a single tool call via MCP Client."""
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        
        # Parse arguments
        try:
            args_str = function.get("arguments", "{}")
            parameters = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.VALIDATION_ERROR,
                error="Invalid tool call arguments"
            )
        
        logger.info(
            "Executing tool",
            tool=tool_name,
            request_id=request_id
        )
        
        # Execute via MCP Client
        result = await self.mcp_client.execute(
            tool_name=tool_name,
            parameters=parameters,
            request_id=request_id
        )
        
        logger.info(
            "Tool executed",
            tool=tool_name,
            status=result.status.value,
            execution_time_ms=result.execution_time_ms
        )
        
        return result
    
    def _format_tool_result(self, result: ToolResult) -> str:
        """Format tool result for conversation context."""
        if result.status == ToolResultStatus.SUCCESS:
            if result.data is None:
                return "Tool executed successfully."
            
            if isinstance(result.data, str):
                return result.data
            
            return json.dumps(result.data, indent=2, default=str)
        else:
            error_msg = result.error or "Unknown error"
            return f"Tool error ({result.status.value}): {error_msg}"
    
    async def get_conversation_history(
        self,
        conversation_id: str
    ) -> list[dict[str, Any]]:
        """Get formatted conversation history."""
        messages = await self.conversations.get_messages(
            conversation_id,
            include_system=False
        )
        
        return [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            }
            for m in messages
        ]
    
    async def end_conversation(self, conversation_id: str) -> bool:
        """End and delete a conversation."""
        return await self.conversations.delete(conversation_id)
    
    async def health_check(self) -> dict[str, Any]:
        """Check gateway health including dependencies."""
        status = {
            "gateway": "healthy",
            "mcp_server": "unknown",
            "tool_count": 0
        }
        
        try:
            health = await self.mcp_client.health_check()
            status["mcp_server"] = health.get("status", "unknown")
            status["tool_count"] = health.get("tool_count", 0)
            status["domains"] = health.get("domains", [])
        except Exception as e:
            status["mcp_server"] = "unhealthy"
            status["mcp_error"] = str(e)
        
        status["conversations"] = self.conversations.get_stats()
        
        return status
