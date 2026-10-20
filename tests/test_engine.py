import json
from unittest.mock import MagicMock
import pytest

from src.core.engine import (
    ConversationEngine,
    EngineEvent,
    ErrorEvent,
    TokenChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
    run_stream,
)
from src.core.ollama_client import ChatMessage, OllamaClient, OllamaConnectionError
from src.features.tools.executor import ToolExecutor
from src.features.tools.registry import ToolRegistry, tool


def test_engine_events_instantiation():
    token_ev = TokenChunkEvent(token="Bonjour")
    assert token_ev.type == "token"
    assert token_ev.token == "Bonjour"

    call_ev = ToolCallEvent(tool_name="get_info", arguments={"id": 42})
    assert call_ev.type == "tool_call"
    assert call_ev.tool_name == "get_info"
    assert call_ev.arguments == {"id": 42}

    res_ev = ToolResultEvent(tool_name="get_info", result={"status": "ok"}, is_error=False)
    assert res_ev.type == "tool_result"
    assert res_ev.result == {"status": "ok"}
    assert res_ev.is_error is False

    err_ev = ErrorEvent(error="Network down", code="ConnErr")
    assert err_ev.type == "error"
    assert err_ev.error == "Network down"


def test_engine_run_stream_without_tools():
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(["Chine ", "antique."])

    engine = ConversationEngine(client=mock_client)
    events = list(engine.run_stream(messages=[{"role": "user", "content": "Test"}], model="qwen2.5:1.5b"))

    assert len(events) == 2
    assert all(isinstance(e, TokenChunkEvent) for e in events)
    assert events[0].token == "Chine "
    assert events[1].token == "antique."
    mock_client.chat_stream.assert_called_once()


def test_engine_run_stream_connection_error_yields_error_event():
    mock_client = MagicMock()
    mock_client.chat_stream.side_effect = OllamaConnectionError("Hôte injoignable")

    engine = ConversationEngine(client=mock_client)
    events = list(engine.run_stream(messages=[{"role": "user", "content": "Test"}], model="qwen2.5:1.5b"))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "Hôte injoignable" in events[0].error


def test_engine_single_tool_call_flow():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def query_wealth(kingdom: str) -> dict[str, int]:
        """Obtient la richesse d'un royaume."""
        return {"wealth": 1000}

    mock_client = MagicMock()
    # Tour 1 : Ollama demande d'appeler l'outil
    turn_1_data = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "query_wealth", "arguments": {"kingdom": "Qin"}},
                    }
                ],
            }
        }
    ]
    # Tour 2 : Ollama répond avec le texte final
    turn_2_data = [
        {"message": {"role": "assistant", "content": "Le royaume de Qin "}},
        {"message": {"role": "assistant", "content": "possède 1000 or."}},
    ]

    mock_client.chat_stream_raw.side_effect = [iter(turn_1_data), iter(turn_2_data)]

    engine = ConversationEngine(client=mock_client, registry=local_registry)
    events = list(
        engine.run_stream(
            messages=[{"role": "user", "content": "Richesse Qin ?"}],
            model="qwen2.5:1.5b",
            tools=local_registry,
        )
    )

    types = [type(e) for e in events]
    assert types == [ToolCallEvent, ToolResultEvent, TokenChunkEvent, TokenChunkEvent]

    call_ev: ToolCallEvent = events[0]
    assert call_ev.tool_name == "query_wealth"
    assert call_ev.arguments == {"kingdom": "Qin"}
    assert call_ev.tool_call_id == "call_1"

    res_ev: ToolResultEvent = events[1]
    assert res_ev.tool_name == "query_wealth"
    assert res_ev.result == {"wealth": 1000}
    assert res_ev.is_error is False

    tokens = "".join(e.token for e in events if isinstance(e, TokenChunkEvent))
    assert tokens == "Le royaume de Qin possède 1000 or."

    assert mock_client.chat_stream_raw.call_count == 2
    # Vérifier que le 2e appel contient le rôle tool avec le résultat
    second_call_messages = mock_client.chat_stream_raw.call_args_list[1][1]["messages"]
    assert len(second_call_messages) == 3
    assert second_call_messages[1]["role"] == "assistant"
    assert second_call_messages[2]["role"] == "tool"
    assert '{"wealth": 1000}' in second_call_messages[2]["content"]


def test_engine_multiple_tool_calls_in_single_turn():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def tool_a(x: int) -> int:
        """Outil A."""
        return x * 2

    @tool(registry=local_registry)
    def tool_b(y: int) -> int:
        """Outil B."""
        return y + 10

    mock_client = MagicMock()
    turn_1_data = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "tool_a", "arguments": {"x": 5}}},
                    {"id": "c2", "function": {"name": "tool_b", "arguments": {"y": 7}}},
                ],
            }
        }
    ]
    turn_2_data = [{"message": {"role": "assistant", "content": "Résultats calculés."}}]

    mock_client.chat_stream_raw.side_effect = [iter(turn_1_data), iter(turn_2_data)]

    engine = ConversationEngine(client=mock_client, registry=local_registry)
    events = list(
        engine.run_stream(
            messages=[{"role": "user", "content": "Calculer"}],
            model="qwen2.5:1.5b",
            tools=local_registry,
        )
    )

    types = [type(e) for e in events]
    assert types == [ToolCallEvent, ToolResultEvent, ToolCallEvent, ToolResultEvent, TokenChunkEvent]

    assert events[0].tool_name == "tool_a"
    assert events[1].result == 10
    assert events[2].tool_name == "tool_b"
    assert events[3].result == 17
    assert events[4].token == "Résultats calculés."


def test_engine_tool_execution_error_propagates_to_tool_message():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def failing_tool(query: str) -> None:
        """Outil qui échoue systématiquement."""
        raise ValueError("Paramètre invalide fourni à l'outil.")

    mock_client = MagicMock()
    turn_1_data = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c_fail", "function": {"name": "failing_tool", "arguments": {"query": "bad"}}},
                ],
            }
        }
    ]
    turn_2_data = [{"message": {"role": "assistant", "content": "Correction après erreur."}}]

    mock_client.chat_stream_raw.side_effect = [iter(turn_1_data), iter(turn_2_data)]

    engine = ConversationEngine(client=mock_client, registry=local_registry)
    events = list(
        engine.run_stream(
            messages=[{"role": "user", "content": "Action"}],
            model="qwen2.5:1.5b",
            tools=local_registry,
        )
    )

    res_ev = next(e for e in events if isinstance(e, ToolResultEvent))
    assert res_ev.is_error is True

    # Vérifier que l'erreur est bien réinjectée dans le rôle tool pour auto-correction
    second_call_messages = mock_client.chat_stream_raw.call_args_list[1][1]["messages"]
    tool_msg = next(m for m in second_call_messages if m.get("role") == "tool")
    assert "Paramètre invalide fourni" in tool_msg["content"]
    assert '"success": false' in tool_msg["content"].lower()


def test_engine_max_tool_iterations_exceeded():
    local_registry = ToolRegistry()

    @tool(registry=local_registry)
    def loop_tool() -> str:
        """Boucle infinie d'appels."""
        return "continue"

    mock_client = MagicMock()
    infinite_loop_data = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "loop_tool", "arguments": {}}}],
            }
        }
    ]

    mock_client.chat_stream_raw.side_effect = [
        iter(infinite_loop_data),
        iter(infinite_loop_data),
        iter(infinite_loop_data),
    ]

    engine = ConversationEngine(client=mock_client, registry=local_registry, max_tool_iterations=3)
    events = list(
        engine.run_stream(
            messages=[{"role": "user", "content": "Boucle"}],
            model="qwen2.5:1.5b",
            tools=local_registry,
        )
    )

    last_event = events[-1]
    assert isinstance(last_event, ErrorEvent)
    assert last_event.code == "MaxToolIterationsExceeded"
