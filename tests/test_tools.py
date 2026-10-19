import json
import pytest
from pydantic import BaseModel, Field

from src.core.db.database import init_database
from src.features.tools.builtin import get_kingdom_info
from src.features.tools.executor import ToolExecutionResult, ToolExecutor
from src.features.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    extract_tool_schema,
    tool,
)


def test_extract_tool_schema_basic():
    def dummy_func(kingdom_name: str, power: int = 100) -> str:
        """Informations d'un royaume.

        :param kingdom_name: Le nom du royaume.
        :param power: Puissance de combat.
        """
        return f"{kingdom_name}: {power}"

    schema = extract_tool_schema(dummy_func)
    assert schema["name"] == "dummy_func"
    assert "Informations d'un royaume" in schema["description"]
    params = schema["parameters"]
    assert params["type"] == "object"
    assert "kingdom_name" in params["required"]
    assert "power" not in params["required"]
    assert params["properties"]["kingdom_name"]["type"] == "string"
    assert params["properties"]["kingdom_name"]["description"] == "Le nom du royaume."
    assert params["properties"]["power"]["type"] == "integer"
    assert params["properties"]["power"]["default"] == 100


def test_tool_decorator_registers_and_attaches_metadata():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def calculate_tribute(amount: int, rate: float = 0.1) -> float:
        """Calcule le tribut annuel.

        :param amount: Montant de base.
        :param rate: Taux applicable.
        """
        return amount * rate

    assert "calculate_tribute" in local_registry
    tool_def = local_registry.get("calculate_tribute")
    assert tool_def is not None
    assert tool_def.name == "calculate_tribute"
    assert "Calcule le tribut annuel" in tool_def.description

    ollama_dict = calculate_tribute.to_ollama_dict()
    assert ollama_dict["type"] == "function"
    assert ollama_dict["function"]["name"] == "calculate_tribute"
    assert "amount" in ollama_dict["function"]["parameters"]["properties"]

    assert calculate_tribute(1000, 0.2) == 200.0


def test_tool_executor_success():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def add_numbers(a: int, b: int) -> dict[str, int]:
        """Additionne deux entiers."""
        return {"sum": a + b}

    executor = ToolExecutor(registry=local_registry)
    res = executor.execute("add_numbers", {"a": 15, "b": 25})
    assert res.success is True
    assert res.result == {"sum": 40}
    assert res.error is None
    parsed = json.loads(res.to_tool_message_content())
    assert parsed["sum"] == 40


def test_tool_executor_unregistered_tool():
    executor = ToolExecutor(registry=ToolRegistry())
    res = executor.execute("unknown_tool", {})
    assert res.success is False
    assert "n'est pas enregistré" in res.error
    content = json.loads(res.to_tool_message_content())
    assert content["success"] is False
    assert "error" in content


def test_tool_executor_execution_exception():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def faulty_action(val: int) -> float:
        """Action avec risque de division par zéro."""
        return 100 / val

    executor = ToolExecutor(registry=local_registry)
    res = executor.execute("faulty_action", {"val": 0})
    assert res.success is False
    assert "ZeroDivisionError" in res.error
    content = json.loads(res.to_tool_message_content())
    assert content["success"] is False
    assert "division by zero" in content["error"]


def test_tool_execution_result_serialization_types():
    class SampleModel(BaseModel):
        field: str

    res_model = ToolExecutionResult(tool_name="t1", success=True, result=SampleModel(field="val"))
    assert '{"field":"val"}' in res_model.to_tool_message_content()

    res_str_json = ToolExecutionResult(tool_name="t2", success=True, result='{"ok": true}')
    assert res_str_json.to_tool_message_content() == '{"ok": true}'

    res_none = ToolExecutionResult(tool_name="t3", success=True, result=None)
    assert json.loads(res_none.to_tool_message_content()) == {"success": True}


def test_builtin_get_kingdom_info():
    init_database()
    res = get_kingdom_info("Qin")
    assert isinstance(res, dict)
    assert res["name"] == "Qin"
    assert res["capital"] == "Xianyang"
    assert res["ruler"] == "Ying Zheng"
    assert "relations" in res

    res_unknown = get_kingdom_info("RoyaumeInconnu")
    assert "error" in res_unknown


def test_registry_mcp_client_registration_and_unregistration():
    registry = ToolRegistry()

    class FakeMCPClient:
        def register_into_registry(self, reg, prefix=""):
            def handler(**kwargs):
                return {"result": "ok"}

            t = ToolDefinition(
                name=f"{prefix}fake_tool",
                description="Fake MCP tool",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
            reg.register(t)
            return [t]

    fake = FakeMCPClient()
    registered = registry.register_mcp_client(fake, prefix="mcp_")
    assert len(registered) == 1
    assert "mcp_fake_tool" in registry

    executor = ToolExecutor(registry=registry)
    exec_res = executor.execute("mcp_fake_tool")
    assert exec_res.success is True
    assert exec_res.result == {"result": "ok"}

    registry.unregister_tools(["mcp_fake_tool"])
    assert "mcp_fake_tool" not in registry
