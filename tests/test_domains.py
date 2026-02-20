"""Tests for application domains."""

import pytest

from shared.models import (
    DomainConfig,
    ExecutionContext,
    ToolResultStatus,
    UserContext,
)


class TestHRDomain:
    """Tests for HR domain."""
    
    def setup_method(self):
        """Set up test fixtures."""
        from domains.hr import HRAdapter
        
        self.config = DomainConfig(
            name="hr",
            description="HR Domain",
            version="1.0.0"
        )
        self.adapter = HRAdapter(self.config)
        self.user = UserContext(
            user_id="test_user",
            username="tester",
            roles=["user"]
        )
        self.context = ExecutionContext(
            request_id="test-req-001",
            user=self.user
        )
    
    def test_get_employee(self):
        """Test getting employee by ID."""
        result = self.adapter.execute(
            "get_employee",
            {"employee_id": "E001"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["name"] == "Alice Johnson"
        assert result.data["department"] == "Engineering"
    
    def test_get_employee_not_found(self):
        """Test getting non-existent employee."""
        result = self.adapter.execute(
            "get_employee",
            {"employee_id": "E999"},
            self.context
        )
        
        assert result.status == ToolResultStatus.ERROR
        assert "not found" in result.error.lower()
    
    def test_search_employees(self):
        """Test searching employees."""
        result = self.adapter.execute(
            "search_employees",
            {"department": "Engineering"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert len(result.data) >= 1
        assert all(e["department"] == "Engineering" for e in result.data)
    
    def test_list_departments(self):
        """Test listing departments."""
        result = self.adapter.execute(
            "list_departments",
            {},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert "Engineering" in result.data
        assert "HR" in result.data
    
    def test_tool_definitions(self):
        """Test that tools are properly defined."""
        tools = self.adapter.tools
        
        assert len(tools) >= 4
        tool_names = [t.name for t in tools]
        assert "get_employee" in tool_names
        assert "search_employees" in tool_names
        assert "list_departments" in tool_names


class TestERPDomain:
    """Tests for ERP domain."""
    
    def setup_method(self):
        """Set up test fixtures."""
        from domains.erp import ERPAdapter
        
        self.config = DomainConfig(
            name="erp",
            description="ERP Domain",
            version="1.0.0"
        )
        self.adapter = ERPAdapter(self.config)
        self.user = UserContext(
            user_id="test_user",
            username="tester",
            roles=["finance"]
        )
        self.context = ExecutionContext(
            request_id="test-req-001",
            user=self.user
        )
    
    def test_get_invoice(self):
        """Test getting invoice by ID."""
        result = self.adapter.execute(
            "get_invoice",
            {"invoice_id": "INV-001"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["customer"] == "Acme Corp"
        assert result.data["amount"] == 15000.00
    
    def test_list_invoices(self):
        """Test listing invoices."""
        result = self.adapter.execute(
            "list_invoices",
            {"status": "pending"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert all(inv["status"] == "pending" for inv in result.data)
    
    def test_create_invoice(self):
        """Test creating an invoice."""
        result = self.adapter.execute(
            "create_invoice",
            {
                "customer": "New Customer",
                "items": [
                    {"description": "Service", "quantity": 2, "unit_price": 100}
                ]
            },
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["success"] is True
        assert result.data["amount"] == 200
        assert "invoice_id" in result.data
    
    def test_get_inventory(self):
        """Test getting inventory item."""
        result = self.adapter.execute(
            "get_inventory",
            {"sku": "SKU-001"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["name"] == "Widget A"
        assert result.data["quantity"] == 500
    
    def test_check_low_stock(self):
        """Test checking low stock items."""
        result = self.adapter.execute(
            "check_low_stock",
            {},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        # SKU-003 has quantity 25, reorder point 50
        low_stock_skus = [item["sku"] for item in result.data]
        assert "SKU-003" in low_stock_skus


class TestDevOpsDomain:
    """Tests for DevOps domain."""
    
    def setup_method(self):
        """Set up test fixtures."""
        from domains.devops import DevOpsAdapter
        
        self.config = DomainConfig(
            name="devops",
            description="DevOps Domain",
            version="1.0.0"
        )
        self.adapter = DevOpsAdapter(self.config)
        self.user = UserContext(
            user_id="test_user",
            username="tester",
            roles=["devops"]
        )
        self.context = ExecutionContext(
            request_id="test-req-001",
            user=self.user
        )
    
    def test_list_pods(self):
        """Test listing pods."""
        result = self.adapter.execute(
            "list_pods",
            {"namespace": "production"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert len(result.data) >= 1
        assert all(pod["status"] in ["Running", "Pending"] for pod in result.data)
    
    def test_get_pod_logs(self):
        """Test getting pod logs."""
        result = self.adapter.execute(
            "get_pod_logs",
            {"pod_name": "api-server-7d8f9b6c5-abc12"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert "logs" in result.data
        assert len(result.data["logs"]) > 0
    
    def test_get_deployment(self):
        """Test getting deployment info."""
        result = self.adapter.execute(
            "get_deployment",
            {"deployment_name": "api-server"},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["name"] == "api-server"
        assert result.data["replicas"] == 2
    
    def test_scale_deployment(self):
        """Test scaling deployment."""
        result = self.adapter.execute(
            "scale_deployment",
            {"deployment_name": "api-server", "replicas": 3},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["success"] is True
        assert result.data["new_replicas"] == 3
    
    def test_get_cluster_health(self):
        """Test getting cluster health."""
        result = self.adapter.execute(
            "get_cluster_health",
            {},
            self.context
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["status"] == "healthy"
        assert "nodes" in result.data
        assert "pods_running" in result.data


class TestDomainIsolation:
    """Tests for domain isolation requirements."""
    
    def test_all_tools_namespaced(self):
        """Test that all tools are properly namespaced."""
        from domains.hr import HRAdapter
        from domains.erp import ERPAdapter
        from domains.devops import DevOpsAdapter
        
        config = DomainConfig(name="test", description="Test", version="1.0.0")
        
        for AdapterClass, domain in [
            (HRAdapter, "hr"),
            (ERPAdapter, "erp"),
            (DevOpsAdapter, "devops")
        ]:
            # Need to override config name for each
            cfg = DomainConfig(name=domain, description="Test", version="1.0.0")
            adapter = AdapterClass(cfg)
            
            for tool in adapter.tools:
                qualified = tool.qualified_name
                assert qualified.startswith(f"{domain}."), \
                    f"Tool {tool.name} should be namespaced as {domain}.{tool.name}"
    
    def test_adapters_have_no_shared_state(self):
        """Test that adapters are independent."""
        from domains.hr import HRAdapter
        from domains.erp import ERPAdapter
        
        hr_config = DomainConfig(name="hr", description="HR", version="1.0.0")
        erp_config = DomainConfig(name="erp", description="ERP", version="1.0.0")
        
        hr_adapter1 = HRAdapter(hr_config)
        hr_adapter2 = HRAdapter(hr_config)
        erp_adapter = ERPAdapter(erp_config)
        
        # Each adapter should have its own tools dict
        assert hr_adapter1._tools is not hr_adapter2._tools
        assert hr_adapter1._tools is not erp_adapter._tools
