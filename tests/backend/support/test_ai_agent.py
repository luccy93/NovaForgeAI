"""AI agent and agent tools tests (Volume 54)."""
import pytest
from app.support.agent_tools import SupportToolRegistry, SupportToolSpec, create_support_tool_registry
from app.support.agent import SupportAgent, support_agent_tool_registry


class TestToolRegistry:
    def test_create_registry(self):
        reg = create_support_tool_registry()
        assert len(reg.list_tools()) > 0
    def test_get_tool(self):
        reg = create_support_tool_registry()
        tool = reg.get("search_knowledge")
        assert tool is not None
        assert tool.name == "search_knowledge"
    def test_get_tool_not_found(self):
        reg = SupportToolRegistry()
        assert reg.get("nonexistent") is None
    def test_describe(self):
        reg = create_support_tool_registry()
        desc = reg.describe()
        assert "search_knowledge" in desc
    def test_describe_with_permissions(self):
        reg = create_support_tool_registry()
        desc = reg.describe(permissions=["knowledge.read"])
        assert "search_knowledge" in desc
    def test_list_tools(self):
        reg = create_support_tool_registry()
        tools = reg.list_tools()
        assert len(tools) >= 10
    def test_validate_call(self):
        reg = create_support_tool_registry()
        assert reg.validate_call("search_knowledge", ["knowledge.read"]) is True
    def test_validate_call_no_permission(self):
        reg = create_support_tool_registry()
        assert reg.validate_call("search_knowledge", ["ticket.read"]) is False
    def test_validate_call_nonexistent(self):
        reg = SupportToolRegistry()
        assert reg.validate_call("nonexistent", ["read"]) is False
    def test_register_custom_tool(self):
        reg = SupportToolRegistry()
        reg.register(SupportToolSpec(
            name="custom_tool", description="Custom", parameters={"x": "str"},
            required_permissions=["custom.perm"],
        ))
        assert reg.get("custom_tool") is not None


class TestSupportAgent:
    def test_agent_config(self):
        agent = SupportAgent()
        assert agent.config.name == "support_agent"
        assert agent.config.temperature == 0.2
    def test_agent_permissions(self):
        agent = SupportAgent()
        assert "ticket.write" in agent.config.permissions
        assert "knowledge.read" in agent.config.permissions
    def test_agent_tool_descriptions(self):
        agent = SupportAgent()
        desc = agent.get_tool_descriptions()
        assert "search_knowledge" in desc
    def test_agent_validate_tool(self):
        agent = SupportAgent()
        assert agent.validate_tool_call("search_knowledge") is True
    def test_agent_tool_registry_singleton(self):
        assert support_agent_tool_registry is not None
        assert len(support_agent_tool_registry.list_tools()) >= 10
