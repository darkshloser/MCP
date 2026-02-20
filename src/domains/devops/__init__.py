"""DevOps Domain - Infrastructure and deployment tools.

Example domain for DevOps operations.
Demonstrates CLI-based adapter pattern.
"""

from datetime import datetime, timedelta
from typing import Any
import random

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


# Sample data for mock implementation
MOCK_PODS = {
    "api-server-7d8f9b6c5-abc12": {
        "name": "api-server-7d8f9b6c5-abc12",
        "namespace": "production",
        "status": "Running",
        "ready": True,
        "restarts": 0,
        "age": "5d",
        "node": "node-01",
        "containers": [
            {"name": "api", "image": "api-server:v2.3.1", "ready": True}
        ]
    },
    "api-server-7d8f9b6c5-def34": {
        "name": "api-server-7d8f9b6c5-def34",
        "namespace": "production",
        "status": "Running",
        "ready": True,
        "restarts": 1,
        "age": "5d",
        "node": "node-02",
        "containers": [
            {"name": "api", "image": "api-server:v2.3.1", "ready": True}
        ]
    },
    "worker-5c4d3b2a1-xyz99": {
        "name": "worker-5c4d3b2a1-xyz99",
        "namespace": "production",
        "status": "Running",
        "ready": True,
        "restarts": 0,
        "age": "3d",
        "node": "node-01",
        "containers": [
            {"name": "worker", "image": "worker:v1.5.0", "ready": True}
        ]
    },
    "db-primary-0": {
        "name": "db-primary-0",
        "namespace": "production",
        "status": "Running",
        "ready": True,
        "restarts": 0,
        "age": "30d",
        "node": "node-03",
        "containers": [
            {"name": "postgres", "image": "postgres:15.2", "ready": True}
        ]
    },
}

MOCK_DEPLOYMENTS = {
    "api-server": {
        "name": "api-server",
        "namespace": "production",
        "replicas": 2,
        "available": 2,
        "ready": 2,
        "image": "api-server:v2.3.1",
        "strategy": "RollingUpdate"
    },
    "worker": {
        "name": "worker",
        "namespace": "production",
        "replicas": 1,
        "available": 1,
        "ready": 1,
        "image": "worker:v1.5.0",
        "strategy": "RollingUpdate"
    },
}

MOCK_LOGS = {
    "api-server-7d8f9b6c5-abc12": [
        "2026-02-09T10:00:00Z INFO Starting API server on port 8080",
        "2026-02-09T10:00:01Z INFO Connected to database",
        "2026-02-09T10:00:02Z INFO Loading configuration",
        "2026-02-09T10:00:03Z INFO Server ready to accept connections",
        "2026-02-09T10:15:00Z INFO GET /health 200 2ms",
        "2026-02-09T10:15:30Z INFO GET /api/users 200 45ms",
    ],
    "worker-5c4d3b2a1-xyz99": [
        "2026-02-09T10:00:00Z INFO Worker starting",
        "2026-02-09T10:00:01Z INFO Connected to message queue",
        "2026-02-09T10:05:00Z INFO Processing job: batch-001",
        "2026-02-09T10:05:30Z INFO Job batch-001 completed successfully",
    ],
}


class DevOpsAdapter(BaseAdapter):
    """
    DevOps Domain Adapter.
    
    Provides tools for:
    - Kubernetes operations (pods, deployments)
    - Log retrieval
    - Scaling operations
    
    In production, this would use kubectl or Kubernetes API.
    """
    
    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self._define_tools()
    
    def _define_tools(self) -> None:
        """Define all DevOps tools."""
        
        # devops.get_pod_logs
        self._tools["get_pod_logs"] = ToolDefinition(
            name="get_pod_logs",
            domain="devops",
            description="Retrieve logs from a Kubernetes pod. Returns recent log lines from the specified pod.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "production"
                    },
                    "container": {
                        "type": "string",
                        "description": "Container name (if pod has multiple containers)"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to retrieve",
                        "default": 100
                    }
                },
                "required": ["pod_name"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "pod": {"type": "string"},
                    "logs": {"type": "array", "items": {"type": "string"}}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(
                level=PermissionLevel.USER,
                roles=["devops", "developer"]
            )
        )
        
        # devops.list_pods
        self._tools["list_pods"] = ToolDefinition(
            name="list_pods",
            domain="devops",
            description="List all pods in a namespace with their status and health information.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "production"
                    },
                    "label_selector": {
                        "type": "string",
                        "description": "Label selector to filter pods (e.g., app=api-server)"
                    }
                },
                "required": []
            },
            output_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                        "ready": {"type": "boolean"}
                    }
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # devops.get_deployment
        self._tools["get_deployment"] = ToolDefinition(
            name="get_deployment",
            domain="devops",
            description="Get detailed information about a Kubernetes deployment.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "deployment_name": {
                        "type": "string",
                        "description": "Name of the deployment"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "production"
                    }
                },
                "required": ["deployment_name"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "replicas": {"type": "integer"},
                    "available": {"type": "integer"},
                    "image": {"type": "string"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # devops.scale_deployment
        self._tools["scale_deployment"] = ToolDefinition(
            name="scale_deployment",
            domain="devops",
            description="Scale a Kubernetes deployment to the specified number of replicas.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "deployment_name": {
                        "type": "string",
                        "description": "Name of the deployment"
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "Target number of replicas",
                        "minimum": 0,
                        "maximum": 100
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "production"
                    }
                },
                "required": ["deployment_name", "replicas"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "previous_replicas": {"type": "integer"},
                    "new_replicas": {"type": "integer"}
                }
            },
            execution_type=ExecutionType.WRITE,
            permissions=Permission(
                level=PermissionLevel.ADMIN,
                roles=["devops", "sre"],
                scopes=["devops:scale"]
            )
        )
        
        # devops.restart_deployment
        self._tools["restart_deployment"] = ToolDefinition(
            name="restart_deployment",
            domain="devops",
            description="Trigger a rolling restart of a deployment.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "deployment_name": {
                        "type": "string",
                        "description": "Name of the deployment"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "production"
                    }
                },
                "required": ["deployment_name"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "message": {"type": "string"}
                }
            },
            execution_type=ExecutionType.WRITE,
            permissions=Permission(
                level=PermissionLevel.ADMIN,
                roles=["devops", "sre"],
                scopes=["devops:restart"]
            )
        )
        
        # devops.get_cluster_health
        self._tools["get_cluster_health"] = ToolDefinition(
            name="get_cluster_health",
            domain="devops",
            description="Get overall health status of the Kubernetes cluster.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {},
                "required": []
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "nodes": {"type": "integer"},
                    "pods_running": {"type": "integer"},
                    "pods_pending": {"type": "integer"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
    
    @property
    def tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())
    
    def execute(
        self,
        action: str,
        parameters: dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """Execute a DevOps action."""
        logger.debug(
            "DevOps action",
            action=action,
            user=context.user.user_id
        )
        
        handlers = {
            "get_pod_logs": self._get_pod_logs,
            "list_pods": self._list_pods,
            "get_deployment": self._get_deployment,
            "scale_deployment": self._scale_deployment,
            "restart_deployment": self._restart_deployment,
            "get_cluster_health": self._get_cluster_health,
        }
        
        handler = handlers.get(action)
        if not handler:
            return self._not_found(action)
        
        try:
            data = handler(parameters, context)
            return ToolResult(
                tool_name=f"devops.{action}",
                status=ToolResultStatus.SUCCESS,
                data=data
            )
        except ValueError as e:
            return ToolResult(
                tool_name=f"devops.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="VALIDATION_ERROR"
            )
        except Exception as e:
            logger.error("DevOps action failed", action=action, error=str(e))
            return ToolResult(
                tool_name=f"devops.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )
    
    def _get_pod_logs(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        pod_name = params.get("pod_name")
        lines = params.get("lines", 100)
        
        if not pod_name:
            raise ValueError("pod_name is required")
        
        if pod_name not in MOCK_PODS:
            raise ValueError(f"Pod {pod_name} not found")
        
        logs = MOCK_LOGS.get(pod_name, [
            f"{datetime.utcnow().isoformat()}Z INFO No logs available"
        ])
        
        return {
            "pod": pod_name,
            "namespace": params.get("namespace", "production"),
            "lines_returned": min(len(logs), lines),
            "logs": logs[-lines:]
        }
    
    def _list_pods(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> list[dict[str, Any]]:
        namespace = params.get("namespace", "production")
        label_selector = params.get("label_selector")
        
        pods = []
        for pod in MOCK_PODS.values():
            if pod["namespace"] != namespace:
                continue
            
            if label_selector:
                # Simple label matching for mock
                if label_selector.split("=")[0] not in pod["name"]:
                    continue
            
            pods.append({
                "name": pod["name"],
                "status": pod["status"],
                "ready": pod["ready"],
                "restarts": pod["restarts"],
                "age": pod["age"],
                "node": pod["node"]
            })
        
        return pods
    
    def _get_deployment(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        deployment_name = params.get("deployment_name")
        
        if not deployment_name:
            raise ValueError("deployment_name is required")
        
        deployment = MOCK_DEPLOYMENTS.get(deployment_name)
        if not deployment:
            raise ValueError(f"Deployment {deployment_name} not found")
        
        return deployment
    
    def _scale_deployment(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        deployment_name = params.get("deployment_name")
        replicas = params.get("replicas")
        
        if not deployment_name:
            raise ValueError("deployment_name is required")
        if replicas is None:
            raise ValueError("replicas is required")
        if replicas < 0 or replicas > 100:
            raise ValueError("replicas must be between 0 and 100")
        
        if deployment_name not in MOCK_DEPLOYMENTS:
            raise ValueError(f"Deployment {deployment_name} not found")
        
        previous = MOCK_DEPLOYMENTS[deployment_name]["replicas"]
        MOCK_DEPLOYMENTS[deployment_name]["replicas"] = replicas
        MOCK_DEPLOYMENTS[deployment_name]["available"] = replicas
        MOCK_DEPLOYMENTS[deployment_name]["ready"] = replicas
        
        return {
            "success": True,
            "deployment": deployment_name,
            "previous_replicas": previous,
            "new_replicas": replicas
        }
    
    def _restart_deployment(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        deployment_name = params.get("deployment_name")
        
        if not deployment_name:
            raise ValueError("deployment_name is required")
        
        if deployment_name not in MOCK_DEPLOYMENTS:
            raise ValueError(f"Deployment {deployment_name} not found")
        
        return {
            "success": True,
            "deployment": deployment_name,
            "message": f"Rolling restart initiated for {deployment_name}"
        }
    
    def _get_cluster_health(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        running = sum(1 for p in MOCK_PODS.values() if p["status"] == "Running")
        pending = sum(1 for p in MOCK_PODS.values() if p["status"] == "Pending")
        
        return {
            "status": "healthy",
            "nodes": 3,
            "nodes_ready": 3,
            "pods_running": running,
            "pods_pending": pending,
            "pods_failed": 0,
            "deployments": len(MOCK_DEPLOYMENTS),
            "deployments_available": len(MOCK_DEPLOYMENTS)
        }


def register_devops_domain(router) -> None:
    """Register the DevOps domain with the MCP server."""
    config = DomainConfig(
        name="devops",
        description="DevOps domain for Kubernetes operations and infrastructure management",
        version="1.0.0"
    )
    
    adapter = DevOpsAdapter(config)
    
    # Register tools
    from mcp_server.registry import get_registry
    registry = get_registry()
    registry.register_many(adapter.tools)
    
    # Register adapter executor
    router.register_adapter("devops", adapter.execute)
    
    logger.info("DevOps domain registered", tool_count=len(adapter.tools))
