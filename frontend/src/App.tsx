import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import api, { ChatMessage } from './services/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isLoading?: boolean;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [domains, setDomains] = useState<string[]>([]);
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load available domains on mount
  useEffect(() => {
    loadDomains();
  }, []);

  const loadDomains = async () => {
    try {
      const response = await api.listTools();
      const domainSet = new Set<string>();
      response.tools.forEach(tool => {
        const name = tool.function.name;
        const domain = name.split('.')[0];
        domainSet.add(domain);
      });
      setDomains(Array.from(domainSet));
    } catch (err) {
      console.error('Failed to load domains:', err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setError(null);
    setIsLoading(true);

    // Add loading indicator
    const loadingMessage: Message = {
      id: 'loading',
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };
    setMessages(prev => [...prev, loadingMessage]);

    try {
      const response = await api.sendMessage(
        userMessage.content,
        conversationId || undefined,
        selectedDomains.length > 0 ? selectedDomains : undefined
      );

      // Update conversation ID
      if (!conversationId) {
        setConversationId(response.conversation_id);
      }

      // Replace loading message with response
      const assistantMessage: Message = {
        id: response.request_id,
        role: 'assistant',
        content: response.response,
        timestamp: new Date(),
      };

      setMessages(prev => 
        prev.filter(m => m.id !== 'loading').concat(assistantMessage)
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      // Remove loading message
      setMessages(prev => prev.filter(m => m.id !== 'loading'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const startNewConversation = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    inputRef.current?.focus();
  };

  const toggleDomain = (domain: string) => {
    setSelectedDomains(prev =>
      prev.includes(domain)
        ? prev.filter(d => d !== domain)
        : [...prev, domain]
    );
  };

  return (
    <div className="flex flex-col h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between max-w-4xl mx-auto">
          <div>
            <h1 className="text-xl font-semibold text-white">MCP Platform</h1>
            <p className="text-sm text-gray-400">AI-powered tool execution</p>
          </div>
          <button
            onClick={startNewConversation}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm transition-colors"
          >
            New Chat
          </button>
        </div>
      </header>

      {/* Domain Filter */}
      {domains.length > 0 && (
        <div className="bg-gray-800 border-b border-gray-700 px-6 py-3">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-gray-400">Domains:</span>
              {domains.map(domain => (
                <button
                  key={domain}
                  onClick={() => toggleDomain(domain)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors ${
                    selectedDomains.includes(domain)
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {domain}
                </button>
              ))}
              {selectedDomains.length > 0 && (
                <button
                  onClick={() => setSelectedDomains([])}
                  className="px-3 py-1 rounded-full text-sm bg-gray-700 text-gray-300 hover:bg-gray-600"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.length === 0 ? (
            <div className="text-center py-20">
              <h2 className="text-2xl font-semibold text-gray-300 mb-2">
                Welcome to MCP Platform
              </h2>
              <p className="text-gray-500 max-w-md mx-auto">
                I can help you with HR queries, ERP operations, and DevOps tasks.
                Try asking about employees, invoices, or pod status.
              </p>
              <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto">
                <ExampleCard
                  title="HR"
                  example="Show me employee E001's details"
                  onClick={() => setInput("Show me employee E001's details")}
                />
                <ExampleCard
                  title="ERP"
                  example="List all pending invoices"
                  onClick={() => setInput("List all pending invoices")}
                />
                <ExampleCard
                  title="DevOps"
                  example="What's the cluster health status?"
                  onClick={() => setInput("What's the cluster health status?")}
                />
              </div>
            </div>
          ) : (
            messages.map(message => (
              <MessageBubble key={message.id} message={message} />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Error display */}
      {error && (
        <div className="px-6 py-2 bg-red-900/50 border-t border-red-700">
          <div className="max-w-4xl mx-auto text-red-300 text-sm">
            {error}
          </div>
        </div>
      )}

      {/* Input */}
      <footer className="bg-gray-800 border-t border-gray-700 px-6 py-4">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          <div className="flex gap-4">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about employees, invoices, deployments..."
              className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 resize-none"
              rows={1}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
            >
              {isLoading ? (
                <LoadingSpinner />
              ) : (
                'Send'
              )}
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-2 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </form>
      </footer>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  if (message.isLoading) {
    return (
      <div className="flex gap-4 message-enter">
        <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center text-white text-sm font-medium">
          AI
        </div>
        <div className="flex-1 bg-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <LoadingSpinner />
            <span className="text-gray-400">Thinking...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-4 message-enter ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${
          isUser ? 'bg-blue-600' : 'bg-green-600'
        }`}
      >
        {isUser ? 'U' : 'AI'}
      </div>
      <div
        className={`flex-1 rounded-lg p-4 ${
          isUser ? 'bg-blue-600' : 'bg-gray-800'
        }`}
      >
        {isUser ? (
          <p className="text-white whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-invert max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function ExampleCard({
  title,
  example,
  onClick,
}: {
  title: string;
  example: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="text-left p-4 bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
    >
      <h3 className="text-sm font-medium text-blue-400 mb-1">{title}</h3>
      <p className="text-sm text-gray-400">{example}</p>
    </button>
  );
}

function LoadingSpinner() {
  return (
    <svg
      className="animate-spin h-5 w-5 text-white"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

export default App;
