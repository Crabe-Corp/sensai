import pytest
from pathlib import Path
from unittest.mock import MagicMock
from src.core import singleton_token
from src.core import memory_management as mem
from src.core.ollama_client import OllamaClient, ChatMessage
from src.features.memory.session_manager import SessionManager, SessionMetadata, ChatSession
from src.interfaces.cli.commands.commands import Commands


def test_consume_tokens_accumulation_and_context_separation():
    singleton_token.budget_tokens = 0
    singleton_token.context_tokens = 0

    # First call: auxiliary / independent call (e.g., /figure Li Xin, 192 tokens)
    mem.consume_tokens(192, is_context=False)
    assert singleton_token.budget_tokens == 192
    assert singleton_token.context_tokens == 0

    # Second call: another auxiliary call (e.g., /figure Qin Shi Huang, 157 tokens)
    mem.consume_tokens(157, is_context=False)
    assert singleton_token.budget_tokens == 349
    assert singleton_token.context_tokens == 0

    # Third call: chat message turn with context tracking (Turn 1: 80 tokens)
    mem.consume_tokens(80, is_context=True)
    assert singleton_token.budget_tokens == 429
    assert singleton_token.context_tokens == 80

    # Fourth call: chat turn 2 (Ollama sends whole history + new Q + new A = 130 tokens)
    # New tokens added are only 130 - 80 = 50 tokens
    mem.consume_tokens(130, is_context=True)
    assert singleton_token.budget_tokens == 429 + 50
    assert singleton_token.context_tokens == 130


def test_ollama_client_track_token_usage_accumulates_budget():
    singleton_token.budget_tokens = 0
    singleton_token.context_tokens = 0

    client = OllamaClient(base_url="http://localhost:11434")

    # Call 1: Figure 1
    call1_data = {
        "prompt_eval_count": 120,
        "eval_count": 72,
        "message": {"role": "assistant", "content": "Li Xin details"}
    }
    client._track_token_usage(call1_data, is_chat_context=False)
    assert singleton_token.budget_tokens == 192
    assert singleton_token.context_tokens == 0

    # Call 2: Figure 2 (157 tokens)
    call2_data = {
        "prompt_eval_count": 100,
        "eval_count": 57,
        "message": {"role": "assistant", "content": "Qin Shi Huang details"}
    }
    client._track_token_usage(call2_data, is_chat_context=False)
    # Budget tokens must accumulate to 349, NOT be overwritten by 157
    assert singleton_token.budget_tokens == 349
    assert singleton_token.context_tokens == 0

    # Call 3: Chat stream or structured chat turn 1
    call3_data = {
        "prompt_eval_count": 210,
        "eval_count": 50,
        "message": {"role": "assistant", "content": "Chat reply 1"}
    }
    client._track_token_usage(call3_data, is_chat_context=True)
    assert singleton_token.budget_tokens == 349 + 260
    assert singleton_token.context_tokens == 260

    # Call 4: Chat turn 2 (Prompt has previous 260 + 20 new query = 280; reply has 40 tokens)
    call4_data = {
        "prompt_eval_count": 280,
        "eval_count": 40,
        "message": {"role": "assistant", "content": "Chat reply 2"}
    }
    client._track_token_usage(call4_data, is_chat_context=True)
    # New tokens added = (280 + 40) - 260 = 60 tokens (NOT 320!)
    assert singleton_token.budget_tokens == 349 + 260 + 60
    assert singleton_token.context_tokens == 320


def test_cli_budget_command_displays_cumulative_consumption(capsys):
    singleton_token.budget_tokens = 349
    cmd = Commands(max_tokens=32768)
    cmd.print_budget()

    out = capsys.readouterr().out
    assert "Token budget : 349 / 32768 consumed." in out


def test_enforce_token_budget_uses_active_context():
    singleton_token.budget_tokens = 30000  # Cumulative budget is large
    singleton_token.context_tokens = 50     # But active conversation context is small

    messages = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there"),
    ]

    mock_client = MagicMock()
    # Context is 50 < 1000 limit, so compression should NOT trigger despite large budget_tokens
    result = mem.enforce_token_budget("dummy_model", mock_client, messages, max_history_tokens=1000)
    assert len(result) == 2
    mock_client.call_model.assert_not_called()


def test_enforce_token_budget_triggers_when_metric_exceeds_threshold():
    singleton_token.budget_tokens = 2000
    singleton_token.context_tokens = 1500

    messages = [
        ChatMessage(role="system", content="System banner"),
        ChatMessage(role="user", content="Question 1"),
        ChatMessage(role="assistant", content="Answer 1"),
        ChatMessage(role="user", content="Question 2"),
        ChatMessage(role="assistant", content="Answer 2"),
    ]

    mock_client = MagicMock()
    mock_client.call_model.return_value = {"message": {"content": "Summary of Q1/A1"}}

    result = mem.enforce_token_budget("dummy_model", mock_client, messages, max_history_tokens=1000)
    # Compression was triggered
    assert len(result) == 4
    assert result[0].content == "System banner"
    assert "Summary of previous exchanges" in result[1].content
    # Metric-only: context_tokens is reset to 0 (no estimation, waits for next real LLM metric)
    assert singleton_token.context_tokens == 0


def test_enforce_token_budget_no_compression_without_metric():
    singleton_token.budget_tokens = 0
    singleton_token.context_tokens = 0  # No metric yet

    messages = [
        ChatMessage(role="system", content="System banner"),
        ChatMessage(role="user", content="Question 1"),
        ChatMessage(role="assistant", content="Answer 1"),
        ChatMessage(role="user", content="Question 2"),
        ChatMessage(role="assistant", content="Answer 2"),
    ]

    mock_client = MagicMock()
    result = mem.enforce_token_budget("dummy_model", mock_client, messages, max_history_tokens=1000)
    # Does not compress because context_tokens is 0 <= 1000
    assert len(result) == len(messages)
    mock_client.call_model.assert_not_called()


def test_session_persistence_preserves_token_metrics(tmp_path: Path):
    manager = SessionManager(storage_dir=tmp_path)
    session = manager.create_session(model="qwen2.5:1.5b", title="Token Session")

    session.metadata.context_tokens = 450
    session.metadata.total_tokens = 600
    manager.save_session(session, sync_remote=False)

    loaded = manager.load_session(session.metadata.session_id)
    assert loaded.metadata.context_tokens == 450
    assert loaded.metadata.total_tokens == 600

    # Simulate /session load in Commands
    singleton_token.context_tokens = 0
    singleton_token.budget_tokens = 0

    cmd = Commands(session_manager=manager, current_session=session)
    cmd.execute_command("/session", f"/session load {session.metadata.session_id}")

    assert singleton_token.context_tokens == 450
    assert singleton_token.budget_tokens == 600
