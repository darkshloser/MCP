/**
 * API service for communicating with the Orchestrator.
 * 
 * The frontend has no business logic - it only captures user input
 * and displays assistant responses.
 */

const API_BASE = '/api';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  conversation_id: string;
  response: string;
  request_id: string;
}

export interface Tool {
  type: string;
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

export interface HealthStatus {
  status: string;
  mcp_server: string;
  tool_count: number;
  conversation_count: number;
}

class ApiService {
  private authToken: string | null = null;

  setAuthToken(token: string | null) {
    this.authToken = token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Request failed: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Send a chat message to the orchestrator.
   */
  async sendMessage(
    message: string,
    conversationId?: string,
    domains?: string[]
  ): Promise<ChatResponse> {
    return this.request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        domains,
      }),
    });
  }

  /**
   * Get conversation history.
   */
  async getConversation(conversationId: string): Promise<{
    conversation_id: string;
    messages: ChatMessage[];
  }> {
    return this.request(`/conversations/${conversationId}`);
  }

  /**
   * List user's conversations.
   */
  async listConversations(): Promise<{
    conversations: Array<{
      id: string;
      user_id: string;
      message_count: number;
      created_at: string;
      updated_at: string;
    }>;
  }> {
    return this.request('/conversations');
  }

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId: string): Promise<void> {
    await this.request(`/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  /**
   * List available tools.
   */
  async listTools(domain?: string): Promise<{
    tools: Tool[];
    count: number;
  }> {
    const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
    return this.request(`/tools${params}`);
  }

  /**
   * Check service health.
   */
  async healthCheck(): Promise<HealthStatus> {
    return this.request('/health');
  }
}

export const api = new ApiService();
export default api;
