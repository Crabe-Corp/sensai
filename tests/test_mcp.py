import json
import sys
from unittest.mock import MagicMock
import pytest

from src.core.engine import ConversationEngine, TokenChunkEvent, ToolCallEvent, ToolResultEvent
from src.features.tools.executor import ToolExecutor
from src.features.tools.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPTool,
)
from src.features.tools.registry import ToolRegistry


def test_mcp_tool_model_and_ollama_conversion():
    raw_schema = {
        "name": "grain_calculator",
        "description": "Calcul du grain",
        "inputSchema": {
            "type": "object",
            "properties": {"soldiers": {"type": "integer"}},
            "required": ["soldiers"],
        },
    }
    tool = MCPTool.model_validate(raw_schema)
    assert tool.name == "grain_calculator"
    assert tool.description == "Calcul du grain"
    assert "soldiers" in tool.input_schema["properties"]

    mock_client = MagicMock()
    mock_client.call_tool.return_value = {"tons": 500}

    tool_def = tool.to_tool_definition(mock_client)
    assert tool_def.name == "grain_calculator"

    ollama_dict = tool_def.to_ollama_dict()
    assert ollama_dict["type"] == "function"
    assert ollama_dict["function"]["name"] == "grain_calculator"
    assert ollama_dict["function"]["parameters"] == tool.input_schema

    res = tool_def.handler(soldiers=1000)
    assert res == {"tons": 500}
    mock_client.call_tool.assert_called_once_with("grain_calculator", {"soldiers": 1000})


def test_mcp_client_invalid_command_raises_connection_error():
    client = MCPClient(["__invalid_non_existent_binary_xyz_123__"])
    with pytest.raises(MCPConnectionError):
        client.start()


def test_mcp_client_call_when_not_started_raises_connection_error():
    client = MCPClient(["python", "--version"])
    with pytest.raises(MCPConnectionError):
        client.call_tool("some_tool", {})


def test_mcp_client_integration_with_demo_server():
    server_cmd = [sys.executable, "-m", "src.features.tools.mcp_server_demo"]

    with MCPClient(server_cmd, default_timeout=10.0) as client:
        assert client.is_connected is True

        tools = client.list_tools()
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "calculate_grain_supply" in tool_names
        assert "get_historical_battle" in tool_names

        # Appel du premier outil MCP : calculate_grain_supply
        grain_res = client.call_tool(
            "calculate_grain_supply",
            {"kingdom": "Qin", "soldiers": 20000, "months": 4},
        )
        assert isinstance(grain_res, dict)
        assert grain_res["kingdom"] == "Qin"
        assert grain_res["soldiers"] == 20000
        assert grain_res["campaign_months"] == 4
        assert grain_res["total_grain_tons"] == 3600.0
        assert grain_res["status"] == "Logistique validée pour la campagne."

        # Appel du second outil MCP : get_historical_battle
        battle_res = client.call_tool("get_historical_battle", {"battle_name": "changping"})
        assert isinstance(battle_res, dict)
        assert battle_res["name"] == "Bataille de Changping"
        assert battle_res["year"] == "-260"
        assert "Bai Qi" in battle_res["commanders"]["Qin"]

        # Enregistrement dynamique dans un ToolRegistry
        registry = ToolRegistry()
        registered_defs = client.register_into_registry(registry, prefix="mcp_")
        assert len(registered_defs) == 2
        assert "mcp_calculate_grain_supply" in registry
        assert "mcp_get_historical_battle" in registry

        # Exécution transparente via ToolExecutor
        executor = ToolExecutor(registry=registry)
        exec_out = executor.execute(
            "mcp_calculate_grain_supply",
            {"kingdom": "Zhao", "soldiers": 10000, "months": 2},
        )
        assert exec_out.success is True
        assert exec_out.result["total_grain_tons"] == 900.0


def test_mcp_client_error_handling_with_demo_server():
    server_cmd = [sys.executable, "-m", "src.features.tools.mcp_server_demo"]

    with MCPClient(server_cmd, default_timeout=10.0) as client:
        with pytest.raises(MCPProtocolError) as exc_info:
            client.call_tool("calculate_grain_supply", {"soldiers": -100})
        assert "doit être strictement supérieur à zéro" in str(exc_info.value)


def test_mcp_full_agent_flow_with_conversation_engine():
    server_cmd = [sys.executable, "-m", "src.features.tools.mcp_server_demo"]

    with MCPClient(server_cmd, default_timeout=10.0) as client:
        registry = ToolRegistry()
        client.register_into_registry(registry)

        mock_ollama = MagicMock()
        turn_1_data = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_mcp_1",
                            "function": {
                                "name": "calculate_grain_supply",
                                "arguments": {"kingdom": "Qin", "soldiers": 10000, "months": 3},
                            },
                        }
                    ],
                }
            }
        ]
        turn_2_data = [
            {"message": {"role": "assistant", "content": "Il faudra 1350 tonnes de grain pour Qin."}}
        ]

        mock_ollama.chat_stream_raw.side_effect = [iter(turn_1_data), iter(turn_2_data)]

        engine = ConversationEngine(client=mock_ollama, registry=registry)
        events = list(
            engine.run_stream(
                messages=[{"role": "user", "content": "Combien de grain pour 10k soldats de Qin ?"}],
                model="qwen2.5:1.5b",
                tools=registry,
            )
        )

        event_types = [type(e) for e in events]
        assert event_types == [ToolCallEvent, ToolResultEvent, TokenChunkEvent]

        tool_call = events[0]
        assert tool_call.tool_name == "calculate_grain_supply"
        assert tool_call.arguments["kingdom"] == "Qin"

        tool_res = events[1]
        assert tool_res.tool_name == "calculate_grain_supply"
        assert tool_res.is_error is False
        assert tool_res.result["total_grain_tons"] == 1350.0

        token_chunk = events[2]
        assert token_chunk.token == "Il faudra 1350 tonnes de grain pour Qin."
