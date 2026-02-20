"""ERP Domain - Enterprise Resource Planning tools and adapter.

Example domain for financial and inventory operations.
"""

from datetime import datetime, timedelta
from typing import Any
import random
import string

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
MOCK_INVOICES = {
    "INV-001": {
        "id": "INV-001",
        "customer": "Acme Corp",
        "amount": 15000.00,
        "currency": "USD",
        "status": "paid",
        "due_date": "2026-01-15",
        "created_date": "2025-12-15",
        "items": [
            {"description": "Consulting Services", "quantity": 10, "unit_price": 1500}
        ]
    },
    "INV-002": {
        "id": "INV-002",
        "customer": "Tech Solutions Inc",
        "amount": 8500.00,
        "currency": "USD",
        "status": "pending",
        "due_date": "2026-02-28",
        "created_date": "2026-01-28",
        "items": [
            {"description": "Software License", "quantity": 5, "unit_price": 1500},
            {"description": "Support Package", "quantity": 1, "unit_price": 1000}
        ]
    },
}

MOCK_INVENTORY = {
    "SKU-001": {
        "sku": "SKU-001",
        "name": "Widget A",
        "category": "Components",
        "quantity": 500,
        "unit_price": 25.00,
        "location": "Warehouse A",
        "reorder_point": 100
    },
    "SKU-002": {
        "sku": "SKU-002",
        "name": "Gadget B",
        "category": "Finished Goods",
        "quantity": 150,
        "unit_price": 199.99,
        "location": "Warehouse B",
        "reorder_point": 50
    },
    "SKU-003": {
        "sku": "SKU-003",
        "name": "Component C",
        "category": "Components",
        "quantity": 25,
        "unit_price": 75.00,
        "location": "Warehouse A",
        "reorder_point": 50
    },
}


class ERPAdapter(BaseAdapter):
    """
    ERP Domain Adapter.
    
    Provides tools for:
    - Invoice management
    - Inventory queries
    - Financial reports
    
    In production, this would connect to an ERP system API.
    """
    
    def __init__(self, config: DomainConfig) -> None:
        super().__init__(config)
        self._define_tools()
    
    def _define_tools(self) -> None:
        """Define all ERP tools."""
        
        # erp.get_invoice
        self._tools["get_invoice"] = ToolDefinition(
            name="get_invoice",
            domain="erp",
            description="Retrieve an invoice by its ID. Returns invoice details including customer, amount, status, and line items.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "The invoice ID (e.g., INV-001)"
                    }
                },
                "required": ["invoice_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "customer": {"type": "string"},
                    "amount": {"type": "number"},
                    "status": {"type": "string"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(
                level=PermissionLevel.USER,
                roles=["finance", "sales"]
            )
        )
        
        # erp.create_invoice
        self._tools["create_invoice"] = ToolDefinition(
            name="create_invoice",
            domain="erp",
            description="Create a new invoice for a customer. Requires customer name, items, and payment terms.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "string",
                        "description": "Customer name"
                    },
                    "items": {
                        "type": "array",
                        "description": "Invoice line items",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "unit_price": {"type": "number"}
                            },
                            "required": ["description", "quantity", "unit_price"]
                        }
                    },
                    "due_days": {
                        "type": "integer",
                        "description": "Payment due in days",
                        "default": 30
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency code",
                        "default": "USD"
                    }
                },
                "required": ["customer", "items"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "invoice_id": {"type": "string"},
                    "amount": {"type": "number"}
                }
            },
            execution_type=ExecutionType.WRITE,
            permissions=Permission(
                level=PermissionLevel.USER,
                roles=["finance", "sales"],
                scopes=["erp:write"]
            )
        )
        
        # erp.list_invoices
        self._tools["list_invoices"] = ToolDefinition(
            name="list_invoices",
            domain="erp",
            description="List invoices with optional filters for status and customer.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status",
                        "enum": ["pending", "paid", "overdue", "cancelled"]
                    },
                    "customer": {
                        "type": "string",
                        "description": "Filter by customer name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 20
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
        
        # erp.get_inventory
        self._tools["get_inventory"] = ToolDefinition(
            name="get_inventory",
            domain="erp",
            description="Get inventory information for a specific SKU.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "Stock Keeping Unit identifier"
                    }
                },
                "required": ["sku"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "name": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "number"}
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # erp.check_low_stock
        self._tools["check_low_stock"] = ToolDefinition(
            name="check_low_stock",
            domain="erp",
            description="Check for items with inventory below reorder point.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category"
                    }
                },
                "required": []
            },
            output_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "name": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "reorder_point": {"type": "integer"}
                    }
                }
            },
            execution_type=ExecutionType.READ,
            permissions=Permission(level=PermissionLevel.USER)
        )
        
        # erp.update_inventory
        self._tools["update_inventory"] = ToolDefinition(
            name="update_inventory",
            domain="erp",
            description="Update inventory quantity for a SKU. Use positive values to add stock, negative to remove.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "Stock Keeping Unit identifier"
                    },
                    "quantity_change": {
                        "type": "integer",
                        "description": "Quantity to add (positive) or remove (negative)"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for inventory change"
                    }
                },
                "required": ["sku", "quantity_change"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "new_quantity": {"type": "integer"}
                }
            },
            execution_type=ExecutionType.WRITE,
            permissions=Permission(
                level=PermissionLevel.USER,
                roles=["inventory", "warehouse"],
                scopes=["erp:write"]
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
        """Execute an ERP action."""
        logger.debug(
            "ERP action",
            action=action,
            user=context.user.user_id
        )
        
        handlers = {
            "get_invoice": self._get_invoice,
            "create_invoice": self._create_invoice,
            "list_invoices": self._list_invoices,
            "get_inventory": self._get_inventory,
            "check_low_stock": self._check_low_stock,
            "update_inventory": self._update_inventory,
        }
        
        handler = handlers.get(action)
        if not handler:
            return self._not_found(action)
        
        try:
            data = handler(parameters, context)
            return ToolResult(
                tool_name=f"erp.{action}",
                status=ToolResultStatus.SUCCESS,
                data=data
            )
        except ValueError as e:
            return ToolResult(
                tool_name=f"erp.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="VALIDATION_ERROR"
            )
        except Exception as e:
            logger.error("ERP action failed", action=action, error=str(e))
            return ToolResult(
                tool_name=f"erp.{action}",
                status=ToolResultStatus.ERROR,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )
    
    def _get_invoice(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        invoice_id = params.get("invoice_id")
        if not invoice_id:
            raise ValueError("invoice_id is required")
        
        invoice = MOCK_INVOICES.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        
        return invoice
    
    def _create_invoice(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        customer = params.get("customer")
        items = params.get("items", [])
        due_days = params.get("due_days", 30)
        currency = params.get("currency", "USD")
        
        if not customer:
            raise ValueError("customer is required")
        if not items:
            raise ValueError("at least one item is required")
        
        # Calculate total
        total = sum(
            item.get("quantity", 0) * item.get("unit_price", 0)
            for item in items
        )
        
        # Generate invoice ID
        invoice_id = f"INV-{''.join(random.choices(string.digits, k=3))}"
        
        # Create invoice (in memory for mock)
        invoice = {
            "id": invoice_id,
            "customer": customer,
            "amount": total,
            "currency": currency,
            "status": "pending",
            "due_date": (datetime.utcnow() + timedelta(days=due_days)).strftime("%Y-%m-%d"),
            "created_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "items": items
        }
        
        MOCK_INVOICES[invoice_id] = invoice
        
        return {
            "success": True,
            "invoice_id": invoice_id,
            "amount": total,
            "currency": currency
        }
    
    def _list_invoices(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> list[dict[str, Any]]:
        status_filter = params.get("status")
        customer_filter = params.get("customer")
        limit = params.get("limit", 20)
        
        results = []
        for invoice in MOCK_INVOICES.values():
            if status_filter and invoice["status"] != status_filter:
                continue
            if customer_filter and customer_filter.lower() not in invoice["customer"].lower():
                continue
            
            results.append({
                "id": invoice["id"],
                "customer": invoice["customer"],
                "amount": invoice["amount"],
                "currency": invoice["currency"],
                "status": invoice["status"],
                "due_date": invoice["due_date"]
            })
            
            if len(results) >= limit:
                break
        
        return results
    
    def _get_inventory(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        sku = params.get("sku")
        if not sku:
            raise ValueError("sku is required")
        
        item = MOCK_INVENTORY.get(sku)
        if not item:
            raise ValueError(f"SKU {sku} not found")
        
        return item
    
    def _check_low_stock(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> list[dict[str, Any]]:
        category_filter = params.get("category")
        
        low_stock = []
        for item in MOCK_INVENTORY.values():
            if category_filter and item["category"] != category_filter:
                continue
            
            if item["quantity"] <= item["reorder_point"]:
                low_stock.append({
                    "sku": item["sku"],
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": item["quantity"],
                    "reorder_point": item["reorder_point"],
                    "location": item["location"]
                })
        
        return low_stock
    
    def _update_inventory(
        self,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> dict[str, Any]:
        sku = params.get("sku")
        quantity_change = params.get("quantity_change")
        reason = params.get("reason", "Manual adjustment")
        
        if not sku:
            raise ValueError("sku is required")
        if quantity_change is None:
            raise ValueError("quantity_change is required")
        
        if sku not in MOCK_INVENTORY:
            raise ValueError(f"SKU {sku} not found")
        
        new_quantity = MOCK_INVENTORY[sku]["quantity"] + quantity_change
        
        if new_quantity < 0:
            raise ValueError(f"Cannot reduce inventory below 0. Current: {MOCK_INVENTORY[sku]['quantity']}")
        
        MOCK_INVENTORY[sku]["quantity"] = new_quantity
        
        return {
            "success": True,
            "sku": sku,
            "previous_quantity": new_quantity - quantity_change,
            "new_quantity": new_quantity,
            "reason": reason
        }


def register_erp_domain(router) -> None:
    """Register the ERP domain with the MCP server."""
    config = DomainConfig(
        name="erp",
        description="Enterprise Resource Planning domain for invoices and inventory",
        version="1.0.0"
    )
    
    adapter = ERPAdapter(config)
    
    # Register tools
    from mcp_server.registry import get_registry
    registry = get_registry()
    registry.register_many(adapter.tools)
    
    # Register adapter executor
    router.register_adapter("erp", adapter.execute)
    
    logger.info("ERP domain registered", tool_count=len(adapter.tools))
