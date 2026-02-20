"""Conversation Manager for the Orchestrator.

Manages conversation state, message history, and context.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from shared.logging import get_logger
from shared.models import Conversation, ConversationMessage, UserContext

logger = get_logger(__name__)


class ConversationManager:
    """
    Manages conversation state for the orchestrator.
    
    Responsibilities:
    - Create and retrieve conversations
    - Add messages to conversations
    - Prune old conversations
    - Provide conversation context for LLM
    """
    
    def __init__(
        self,
        max_conversation_length: int = 50,
        conversation_ttl_minutes: int = 60
    ) -> None:
        """
        Initialize conversation manager.
        
        Args:
            max_conversation_length: Maximum messages per conversation
            conversation_ttl_minutes: Conversation time-to-live
        """
        self.max_length = max_conversation_length
        self.ttl = timedelta(minutes=conversation_ttl_minutes)
        
        self._conversations: dict[str, Conversation] = {}
        self._lock = asyncio.Lock()
    
    async def create(
        self,
        user: UserContext,
        system_prompt: Optional[str] = None
    ) -> Conversation:
        """
        Create a new conversation.
        
        Args:
            user: User context
            system_prompt: Optional system prompt to start the conversation
        
        Returns:
            New conversation instance
        """
        conversation_id = str(uuid.uuid4())
        
        messages = []
        if system_prompt:
            messages.append(ConversationMessage(
                role="system",
                content=system_prompt
            ))
        
        conversation = Conversation(
            id=conversation_id,
            user=user,
            messages=messages
        )
        
        async with self._lock:
            self._conversations[conversation_id] = conversation
        
        logger.info(
            "Conversation created",
            conversation_id=conversation_id,
            user=user.user_id
        )
        
        return conversation
    
    async def get(self, conversation_id: str) -> Optional[Conversation]:
        """
        Get a conversation by ID.
        
        Args:
            conversation_id: Conversation identifier
        
        Returns:
            Conversation if found and not expired, None otherwise
        """
        conversation = self._conversations.get(conversation_id)
        
        if conversation is None:
            return None
        
        # Check if expired
        if datetime.utcnow() - conversation.updated_at > self.ttl:
            await self.delete(conversation_id)
            return None
        
        return conversation
    
    async def get_or_create(
        self,
        conversation_id: Optional[str],
        user: UserContext,
        system_prompt: Optional[str] = None
    ) -> Conversation:
        """
        Get existing conversation or create new one.
        
        Args:
            conversation_id: Optional conversation ID to retrieve
            user: User context for new conversations
            system_prompt: System prompt for new conversations
        
        Returns:
            Conversation instance
        """
        if conversation_id:
            conversation = await self.get(conversation_id)
            if conversation:
                return conversation
        
        return await self.create(user, system_prompt)
    
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None
    ) -> Optional[ConversationMessage]:
        """
        Add a message to a conversation.
        
        Args:
            conversation_id: Conversation identifier
            role: Message role (user, assistant, system, tool)
            content: Message content
            tool_calls: Optional tool calls from assistant
            tool_call_id: Optional tool call ID for tool responses
        
        Returns:
            Added message if successful, None otherwise
        """
        conversation = await self.get(conversation_id)
        if not conversation:
            return None
        
        message = ConversationMessage(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id
        )
        
        async with self._lock:
            conversation.messages.append(message)
            conversation.updated_at = datetime.utcnow()
            
            # Prune if over limit (keep system message)
            if len(conversation.messages) > self.max_length:
                system_msgs = [m for m in conversation.messages if m.role == "system"]
                other_msgs = [m for m in conversation.messages if m.role != "system"]
                
                # Keep recent messages
                keep_count = self.max_length - len(system_msgs)
                conversation.messages = system_msgs + other_msgs[-keep_count:]
        
        return message
    
    async def add_user_message(
        self,
        conversation_id: str,
        content: str
    ) -> Optional[ConversationMessage]:
        """Add a user message to the conversation."""
        return await self.add_message(conversation_id, "user", content)
    
    async def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None
    ) -> Optional[ConversationMessage]:
        """Add an assistant message to the conversation."""
        return await self.add_message(
            conversation_id, "assistant", content, tool_calls=tool_calls
        )
    
    async def add_tool_result(
        self,
        conversation_id: str,
        tool_call_id: str,
        content: str
    ) -> Optional[ConversationMessage]:
        """Add a tool result to the conversation."""
        return await self.add_message(
            conversation_id, "tool", content, tool_call_id=tool_call_id
        )
    
    async def get_messages(
        self,
        conversation_id: str,
        include_system: bool = True
    ) -> list[ConversationMessage]:
        """
        Get all messages in a conversation.
        
        Args:
            conversation_id: Conversation identifier
            include_system: Whether to include system messages
        
        Returns:
            List of messages
        """
        conversation = await self.get(conversation_id)
        if not conversation:
            return []
        
        messages = conversation.messages
        if not include_system:
            messages = [m for m in messages if m.role != "system"]
        
        return messages
    
    async def delete(self, conversation_id: str) -> bool:
        """
        Delete a conversation.
        
        Args:
            conversation_id: Conversation identifier
        
        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            if conversation_id in self._conversations:
                del self._conversations[conversation_id]
                logger.info("Conversation deleted", conversation_id=conversation_id)
                return True
        return False
    
    async def cleanup_expired(self) -> int:
        """
        Remove expired conversations.
        
        Returns:
            Number of conversations removed
        """
        now = datetime.utcnow()
        expired = []
        
        async with self._lock:
            for conv_id, conv in self._conversations.items():
                if now - conv.updated_at > self.ttl:
                    expired.append(conv_id)
            
            for conv_id in expired:
                del self._conversations[conv_id]
        
        if expired:
            logger.info("Expired conversations cleaned up", count=len(expired))
        
        return len(expired)
    
    async def list_conversations(
        self,
        user_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        List conversations, optionally filtered by user.
        
        Args:
            user_id: Optional user ID filter
        
        Returns:
            List of conversation summaries
        """
        conversations = list(self._conversations.values())
        
        if user_id:
            conversations = [c for c in conversations if c.user.user_id == user_id]
        
        return [
            {
                "id": c.id,
                "user_id": c.user.user_id,
                "message_count": len(c.messages),
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat()
            }
            for c in conversations
        ]
    
    def get_stats(self) -> dict[str, Any]:
        """Get conversation manager statistics."""
        return {
            "total_conversations": len(self._conversations),
            "max_length": self.max_length,
            "ttl_minutes": self.ttl.total_seconds() / 60
        }
