"""HR Domain - Human Resources tools and adapter.

Example domain for employee management operations.
Demonstrates:
- Tool definitions with proper namespacing
- Adapter implementation
- Permission model
"""

from typing import Any

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
MOCK_EMPLOYEES = {
    "E001": {
        "id": "E001",
        "name": "Alice Johnson",
        "email": "alice.johnson@company.com",
        "department": "Engineering",
        "position": "Senior Developer",
        "manager": "E010",
        "start_date": "2020-03-15",
        "status": "active"
    },
    "E002": {
        "id": "E002",
        "name": "Bob Smith",
        "email": "bob.smith@company.com",
        "department": "Engineering",
        "position": "Tech Lead",
        "manager": "E010",
        "start_date": "2019-06-01",
        "status": "active"
    },
    "E003": {
        "id": "E003",
        "name": "Carol Williams",
        "email": "carol.williams@company.com",
        "department": "HR",
        "position": "HR Manager",
        "manager": "E020",
        "start_date": "2018-01-10",
        "status": "active"
    },
}

MOCK_DEPARTMENTS = {
    "Engineering": {"head": "E010", "employee_count": 25, "budget": 2500000},
    "HR": {"head": "E020", "employee_count": 5, "budget": 500000},
    "Finance": {"head": "E030", "employee_count": 10, "budget": 800000},
    "Marketing": {"head": "E040", "employee_count": 15, "budget": 1200000},
}


class HRAdapter(BaseAdapter):
    """
    HR Domain Adapter.
    
    Provides tools for:
    - Employee lookup and search
    - Department information
    - Organization structure
    
    In production, this would connect to an HR system API.
    """
    
    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self._define_tools()
    
    def _define_tools(self) -> None:
        """Define all HR tools."""
        
        # hr.get_employee
        self._tools["get_employee"] = ToolDefinition(
            name="get_employee",
            domain="hr",
            description="Get detailed information about an employee by their ID. Returns employee name, email, department, position, and status.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "The unique employee identifier (e.g., E001)"
                    }
                },
                "required": ["employee_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "department": {"type": "string"},
                    "position": {"type": "string"},
                    "status": {"type": "string"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER),
            examples=[
                {"input": {"employee_id": "E001"}, "description": "Get employee E001"}
            ]
        )
        
        # hr.search_employees
        self._tools["search_employees"] = ToolDefinition(
            name="search_employees",
            domain="hr",
            description="Search for employees by name, department, or position. Returns a list of matching employees.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (name, department, or position)"
                    },
                    "department": {
                        "type": "string",
                        "description": "Filter by department name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10
                    }
                },
                "required": []
            },
            output_schema={
                "type": "array",
                "items": {"type": "object"}
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # hr.get_department
        self._tools["get_department"] = ToolDefinition(
            name="get_department",
            domain="hr",
            description="Get information about a department including head, employee count, and budget.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "department_name": {
                        "type": "string",
                        "description": "Name of the department"
                    }
                },
                "required": ["department_name"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "head": {"type": "string"},
                    "employee_count": {"type": "integer"},
                    "budget": {"type": "number"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # hr.list_departments
        self._tools["list_departments"] = ToolDefinition(
            name="list_departments",
            domain="hr",
            description="List all departments in the organization.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {},
                "required": []
            },
            output_schema={
                "type": "array",
                "items": {"type": "string"}
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.PUBLIC)
        )
        
        # hr.update_employee (write operation, requires admin)
        self._tools["update_employee"] = ToolDefinition(
            name="update_employee",
            domain="hr",
            description="Update employee information. Requires HR admin permissions.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "The employee ID to update"
                    },
                    "position": {
                        "type": "string",
                        "description": "New position/title"
                    },
                    "department": {
                        "type": "string",
                        "description": "New department"
                    },
                    "manager": {
                        "type": "string",
                        "description": "New manager employee ID"
                    }
                },
                "required": ["employee_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "employee": {"type": "object"}
                }
            },
            execution_type=ExecutionType.WRITE,
            permissions=Permission(
                level=PermissionLevel.ADMIN,
                roles=["hr_admin"],
                scopes=["hr:write"]
            )
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
        """Execute an HR action."""
        logger.debug(
            "HR action",
            action=action,
            user=context.user.user_id
        )
        
        handlers = {
            "get_employee": self._get_employee,
            "search_employees": self._search_employees,
            "get_department": self._get_department,
            "list_departments": self._list_departments,
            "update_employee": self._update_employee,
        }
        
        handler = handlers.get(action)
        if not handler:
            return self._not_found(action)
        
        try:
            data = handler(parameters, context)
            return ToolResult(
                tool_name=f"hr.{action}",
                status=ToolResultStatus.SUCCESS,
                data=data
            )
        except ValueError as e:
            return ToolResult(
                tool_name=f"hr.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="VALIDATION_ERROR"
            )
        except Exception as e:
            logger.error("HR action failed", action=action, error=str(e))
            return ToolResult(
                tool_name=f"hr.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )
    
    def _get_employee(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        if not employee_id:
            raise ValueError("employee_id is required")
        
        employee = MOCK_EMPLOYEES.get(employee_id)
        if not employee:
            raise ValueError(f"Employee {employee_id} not found")
        
        return employee
    
    def _search_employees(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> list[dict[str, Any]]:
        query = params.get("query", "").lower()
        department = params.get("department")
        limit = params.get("limit", 10)
        
        results = []
        for emp in MOCK_EMPLOYEES.values():
            # Filter by department
            if department and emp["department"] != department:
                continue
            
            # Filter by query
            if query:
                searchable = f"{emp['name']} {emp['position']} {emp['department']}".lower()
                if query not in searchable:
                    continue
            
            results.append(emp)
            
            if len(results) >= limit:
                break
        
        return results
    
    def _get_department(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        dept_name = params.get("department_name")
        if not dept_name:
            raise ValueError("department_name is required")
        
        dept = MOCK_DEPARTMENTS.get(dept_name)
        if not dept:
            raise ValueError(f"Department {dept_name} not found")
        
        return {"name": dept_name, **dept}
    
    def _list_departments(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> list[str]:
        return list(MOCK_DEPARTMENTS.keys())
    
    def _update_employee(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        if not employee_id:
            raise ValueError("employee_id is required")
        
        if employee_id not in MOCK_EMPLOYEES:
            raise ValueError(f"Employee {employee_id} not found")
        
        # In a real implementation, this would update the employee
        # For mock, just return success with updated data
        employee = MOCK_EMPLOYEES[employee_id].copy()
        
        if "position" in params:
            employee["position"] = params["position"]
        if "department" in params:
            employee["department"] = params["department"]
        if "manager" in params:
            employee["manager"] = params["manager"]
        
        return {"success": True, "employee": employee}


def register_hr_domain(router) -> None:
    """Register the HR domain with the MCP server."""
    config = DomainConfig(
        name="hr",
        description="Human Resources domain for employee and department management",
        version="1.0.0"
    )
    
    adapter = HRAdapter(config)
    
    # Register tools
    from mcp_server.registry import get_registry
    registry = get_registry()
    registry.register_many(adapter.tools)
    
    # Register adapter executor
    router.register_adapter("hr", adapter.execute)
    
    logger.info("HR domain registered", tool_count=len(adapter.tools))
