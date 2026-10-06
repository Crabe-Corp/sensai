import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.cli.main import (
    load_config_file,
    parse_arguments,
    resolve_configuration,
    run_session,
)
from src.core.ollama_client import (
    ChatMessage,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)


def test_parse_arguments():
    args = parse_arguments(["--model", "llama3:latest", "--host", "http://127.0.0.1:11434"])
    assert args.model == "llama3:latest"
    assert args.host == "http://127.0.0.1:11434"
    assert args.config == "config.json"


def test_resolve_configuration_cli_priority(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"ollama_host": "http://cfg-host:11434", "default_model": "cfg-model"}')

    monkeypatch.setenv("SENSAI_HOST", "http://env-host:11434")
    monkeypatch.setenv("SENSAI_MODEL", "env-model")

    # Si arguments CLI présents, ils écrasent tout
    args = argparse.Namespace(model="cli-model", host="http://cli-host:11434", config=str(cfg_file))
    host, model = resolve_configuration(args)
    assert host == "http://cli-host:11434"
    assert model == "cli-model"


def test_resolve_configuration_env_priority(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"ollama_host": "http://cfg-host:11434", "default_model": "cfg-model"}')

    monkeypatch.setenv("SENSAI_HOST", "http://env-host:11434")
    monkeypatch.setenv("SENSAI_MODEL", "env-model")

    # Pas d'arguments CLI : l'ENV a la priorité sur le fichier de config
    args = argparse.Namespace(model=None, host=None, config=str(cfg_file))
    host, model = resolve_configuration(args)
    assert host == "http://env-host:11434"
    assert model == "env-model"


def test_resolve_configuration_file_priority(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"ollama_host": "http://cfg-host:11434", "default_model": "cfg-model"}')

    monkeypatch.delenv("SENSAI_HOST", raising=False)
    monkeypatch.delenv("SENSAI_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    args = argparse.Namespace(model=None, host=None, config=str(cfg_file))
    host, model = resolve_configuration(args)
    assert host == "http://cfg-host:11434"
    assert model == "cfg-model"


def test_resolve_configuration_defaults(monkeypatch):
    monkeypatch.delenv("SENSAI_HOST", raising=False)
    monkeypatch.delenv("SENSAI_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    args = argparse.Namespace(model=None, host=None, config="non_existent.json")
    host, model = resolve_configuration(args)
    assert host == "http://localhost:11434"
    assert model == "qwen2.5:1.5b"


def test_run_session_exit_command():
    mock_client = MagicMock()
    with patch("builtins.input", side_effect=["/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")
    mock_client.chat_stream.assert_not_called()


def test_run_session_empty_input_then_exit():
    mock_client = MagicMock()
    with patch("builtins.input", side_effect=["   ", "/quit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")
    mock_client.chat_stream.assert_not_called()


def test_run_session_chat_exchange():
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(["Hello", " world!"])

    with patch("builtins.input", side_effect=["Salut", "/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")

    mock_client.chat_stream.assert_called_once()
    args, kwargs = mock_client.chat_stream.call_args
    assert kwargs["model"] == "qwen2.5:1.5b"
    assert len(kwargs["messages"]) == 1
    assert kwargs["messages"][0].role == "user"
    assert kwargs["messages"][0].content == "Salut"


def test_run_session_connection_error_handling():
    mock_client = MagicMock()
    mock_client.chat_stream.side_effect = OllamaConnectionError("Connexion échouée")

    with patch("builtins.input", side_effect=["Question", "/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")

    mock_client.chat_stream.assert_called_once()


def test_run_session_model_not_found_handling():
    mock_client = MagicMock()
    mock_client.chat_stream.side_effect = OllamaModelNotFoundError("Modèle inexistant")

    with patch("builtins.input", side_effect=["Question", "/exit"]):
        run_session(mock_client, model="inconnu", host="http://localhost:11434")

    mock_client.chat_stream.assert_called_once()


def test_run_session_internal_commands():
    mock_client = MagicMock()
    mock_client.list_models.return_value = ["qwen2.5:1.5b"]

    with patch("builtins.input", side_effect=["/help", "/history", "/models", "/clear", "/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")

    mock_client.list_models.assert_called_once()
    mock_client.chat_stream.assert_not_called()


def test_run_session_keyboard_interrupt_exit():
    mock_client = MagicMock()
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")
    mock_client.chat_stream.assert_not_called()


def test_run_session_change_model_command():
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(["Réponse"])

    with patch("builtins.input", side_effect=["/model", "/model mistral", "Test message", "/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")

    mock_client.chat_stream.assert_called_once()
    args, kwargs = mock_client.chat_stream.call_args
    assert kwargs["model"] == "mistral"


def test_parse_arguments_tools_flag():
    args = parse_arguments(["--tools"])
    assert args.tools is True


def test_run_session_tools_commands(capsys):
    mock_client = MagicMock()
    with patch("builtins.input", side_effect=["/tools", "/tools on", "/tools off", "/exit"]):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")

    captured = capsys.readouterr()
    assert "Outils enregistrés" in captured.out
    assert "get_kingdom_info" in captured.out
    assert "Outils MCP activés" in captured.out
    assert "Outils MCP désactivés" in captured.out


def test_interfaces_cli_main_direct_import():
    from src.interfaces.cli.main import main as iface_main, run_session as iface_run_session
    assert callable(iface_main)
    assert callable(iface_run_session)

