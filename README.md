# MCP Platform

A scalable MCP-based execution platform that allows users to interact via a chat UI, with an LLM (via LlamaIndex) interpreting intent and controlled execution of application-specific actions via MCP.

## Architecture Overview

```
┌─────────────┐
│   Chat UI   │  React-based frontend
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Orchestrator (AI Gateway)  │  FastAPI - Conversation management, LLM orchestration
└──────┬──────────────────────┘
       │
       ├────────────────────┐
       ▼                    ▼
┌─────────────┐      ┌─────────────┐
│     LLM     │      │ MCP Client  │
│ (LlamaIndex)│      │             │
└─────────────┘      └──────┬──────┘
                            │
                            ▼
                     ┌─────────────┐
                     │ MCP Server  │  Tool registry, auth, audit, routing
                     └──────┬──────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    ┌───────────┐    ┌───────────┐    ┌───────────┐
    │    HR     │    │    ERP    │    │  DevOps   │
    │  Domain   │    │  Domain   │    │  Domain   │
    └───────────┘    └───────────┘    └───────────┘
```

## Key Principles

- **Separation of Concerns**: Each component has a single responsibility
- **Domain Isolation**: Applications are isolated with no cross-domain calls
- **Configuration-Driven**: New domains added via configuration, not code changes
- **LLM is Advisory, MCP is Authoritative**: LLM suggests actions, MCP enforces them

## Components

### Frontend (Chat UI)
- Captures user input
- Displays assistant responses
- No business logic
- No direct LLM or MCP access

### Orchestrator (AI Gateway)
- Manages conversation state
- Interfaces with LLM via LlamaIndex
- Supplies tool definitions to LLM
- Parses structured tool calls
- Invokes MCP Client

### MCP Server
- Registers and exposes MCP tools
- Enforces authorization
- Routes calls to application domains
- Audits all executions
- No LLM or UI logic

### Application Domains
Each domain contains:
- Tool definitions (namespaced, e.g., `hr.get_employee`)
- Adapter implementation
- Permission model
- Configuration

Included domains:
- **HR**: Employee lookup, department info
- **ERP**: Invoices, inventory management
- **DevOps**: Kubernetes operations, logs, scaling

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker (optional)

### Local Development

1. **Clone and setup**:
```bash
cd mcp_poc
cp .env.example .env
# Edit .env with your LLM API keys
```

2. **Install Python dependencies**:
```bash
pip install -e ".[dev]"
```

3. **Start MCP Server** (terminal 1):
```bash
export PYTHONPATH=$PWD/src
python -m mcp_server.main
```

4. **Start Orchestrator** (terminal 2):
```bash
export PYTHONPATH=$PWD/src
python -m orchestrator.main
```

5. **Start Frontend** (terminal 3):
```bash
cd frontend
npm install
npm run dev
```

6. **Open browser**: http://localhost:3000

### Using Docker

```bash
# Build and run all services
docker-compose up --build

# Access:
# - Frontend: http://localhost:3000
# - Orchestrator API: http://localhost:8000
# - MCP Server API: http://localhost:8001
```

### Testing with Mock LLM

For testing without LLM API keys, use the mock provider:

```yaml
# config/settings.yaml
llm:
  provider: mock
```

## API Endpoints

### Orchestrator (port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/chat` | POST | Send chat message |
| `/conversations` | GET | List conversations |
| `/conversations/{id}` | GET | Get conversation history |
| `/conversations/{id}` | DELETE | Delete conversation |
| `/tools` | GET | List available tools |

### MCP Server (port 8001)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/tools` | GET | List registered tools |
| `/tools/{name}` | GET | Get tool details |
| `/execute` | POST | Execute a tool |
| `/domains` | GET | List registered domains |

## Tool Examples

### HR Domain

```python
# Get employee information
hr.get_employee(employee_id="E001")

# Search employees
hr.search_employees(department="Engineering", query="developer")

# List departments
hr.list_departments()
```

### ERP Domain

```python
# Get invoice
erp.get_invoice(invoice_id="INV-001")

# Create invoice
erp.create_invoice(
    customer="Acme Corp",
    items=[{"description": "Service", "quantity": 1, "unit_price": 1000}]
)

# Check low stock
erp.check_low_stock(category="Components")
```

### DevOps Domain

```python
# List pods
devops.list_pods(namespace="production")

# Get pod logs
devops.get_pod_logs(pod_name="api-server-xyz")

# Scale deployment
devops.scale_deployment(deployment_name="api-server", replicas=3)
```

## Adding a New Domain

1. **Create domain directory**:
```
src/domains/mydomain/
├── __init__.py
└── config.yaml (optional)
```

2. **Implement adapter**:
```python
# src/domains/mydomain/__init__.py
from domains.base import BaseAdapter
from shared.models import DomainConfig, ToolDefinition

class MyDomainAdapter(BaseAdapter):
    def __init__(self, config: DomainConfig):
        super().__init__(config)
        self._define_tools()
    
    def _define_tools(self):
        self._tools["my_action"] = ToolDefinition(
            name="my_action",
            domain="mydomain",
            description="Does something useful",
            input_schema={...},
            output_schema={...}
        )
    
    @property
    def tools(self):
        return list(self._tools.values())
    
    def execute(self, action, parameters, context):
        # Implement action handlers
        ...

def register_mydomain_domain(router):
    config = DomainConfig(name="mydomain", ...)
    adapter = MyDomainAdapter(config)
    
    from mcp_server.registry import get_registry
    get_registry().register_many(adapter.tools)
    router.register_adapter("mydomain", adapter.execute)
```

3. **Register in `domains/__init__.py`**:
```python
from domains.mydomain import register_mydomain_domain

def load_all_domains(router):
    # ... existing domains ...
    register_mydomain_domain(router)
```

4. **Add configuration** (optional):
```yaml
# config/domains/mydomain.yaml
name: mydomain
description: My custom domain
version: "1.0.0"
enabled: true
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_ENVIRONMENT` | Environment name | development |
| `MCP_LOG_LEVEL` | Log level | INFO |
| `LLM_PROVIDER` | LLM provider | azure_openai |
| `LLM_API_KEY` | API key for LLM | - |
| `LLM_API_BASE` | API base URL | - |
| `LLM_MODEL` | Model name | gpt-4 |
| `MCP_SERVER_PORT` | MCP Server port | 8001 |
| `ORCHESTRATOR_PORT` | Orchestrator port | 8000 |

### YAML Configuration

See `config/settings.yaml` for full configuration options.

## Security

### Authentication
- User identity originates in Orchestrator
- MCP Server trusts only authenticated MCP Clients
- JWT-based token authentication

### Authorization
- Enforced in MCP Server
- Never decided by the LLM
- Role-based and scope-based access control

### Auditing
- All tool executions are logged
- Captures: user, tool, parameters, timestamp, result
- Sensitive parameters are automatically redacted

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_domains.py

# Run specific test
pytest tests/test_mcp_server.py::TestToolRegistry::test_register_tool
```

## Project Structure

```
mcp_poc/
├── src/
│   ├── shared/              # Shared models, config, utilities
│   │   ├── models.py        # Pydantic models
│   │   ├── config.py        # Configuration management
│   │   ├── logging.py       # Structured logging
│   │   └── schema.py        # JSON Schema utilities
│   ├── mcp_server/          # MCP Server
│   │   ├── main.py          # FastAPI app
│   │   ├── registry.py      # Tool registry
│   │   ├── router.py        # Tool routing
│   │   ├── auth.py          # Authentication/Authorization
│   │   └── audit.py         # Audit logging
│   ├── mcp_client/          # MCP Client
│   │   ├── client.py        # HTTP client
│   │   └── discovery.py     # Tool discovery with caching
│   ├── orchestrator/        # AI Gateway
│   │   ├── main.py          # FastAPI app
│   │   ├── llm.py           # LLM providers (LlamaIndex)
│   │   ├── conversation.py  # Conversation management
│   │   └── gateway.py       # Core orchestration logic
│   └── domains/             # Application domains
│       ├── base.py          # Base adapter classes
│       ├── hr/              # HR domain
│       ├── erp/             # ERP domain
│       └── devops/          # DevOps domain
├── frontend/                # React chat UI
│   ├── src/
│   │   ├── App.tsx          # Main component
│   │   └── services/api.ts  # API client
│   └── package.json
├── config/                  # Configuration files
│   ├── settings.yaml        # Main config
│   └── domains/             # Domain configs
├── tests/                   # Test suite
├── docker-compose.yml       # Docker orchestration
├── Dockerfile              # Backend container
└── pyproject.toml          # Python project config
```

## Success Criteria

✅ New applications onboarded via new domain only  
✅ No core redeployment for extensions  
✅ LLM provider swappable without MCP changes  
✅ Safe coexistence of multiple applications  
✅ Domain isolation by design  
✅ Configuration-driven extensibility  

## License

MIT License - see [LICENSE](LICENSE) for details.