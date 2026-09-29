import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.core.ollama_client import (
    ChatMessage,
    OllamaAPIError,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)


def test_chat_message_validation():
    msg = ChatMessage(role="user", content="Hello world")
    assert msg.role == "user"
    assert msg.content == "Hello world"

    with pytest.raises(Exception):
        ChatMessage(role="invalid_role", content="Hello")


def test_check_connection_success():
    client = OllamaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(client._client, "get", return_value=mock_resp) as mock_get:
        assert client.check_connection() is True
        mock_get.assert_called_once_with("http://localhost:11434/api/version", timeout=2.0)
    client.close()


def test_check_connection_failure():
    client = OllamaClient()
    with patch.object(client._client, "get", side_effect=httpx.ConnectError("Refused")):
        assert client.check_connection() is False
    client.close()


def test_list_models_success():
    client = OllamaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:1.5b"}, {"name": "llama3:latest"}]
    }

    with patch.object(client._client, "get", return_value=mock_resp):
        models = client.list_models()
        assert models == ["qwen2.5:1.5b", "llama3:latest"]
    client.close()


def test_chat_stream_success():
    client = OllamaClient()
    mock_lines = [
        json.dumps({"message": {"content": "Bonjour "}}),
        json.dumps({"message": {"content": "voyageur !"}}),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.iter_lines.return_value = iter(mock_lines)

    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__.return_value = mock_response

    with patch.object(client._client, "stream", return_value=mock_stream_cm):
        chunks = list(
            client.chat_stream(
                model="qwen2.5:1.5b",
                messages=[ChatMessage(role="user", content="Salutations")],
            )
        )
        assert chunks == ["Bonjour ", "voyageur !"]
    client.close()


def test_chat_stream_connection_error():
    client = OllamaClient()
    with patch.object(
        client._client,
        "stream",
        side_effect=httpx.ConnectError("Serveur éteint"),
    ):
        with pytest.raises(OllamaConnectionError):
            list(
                client.chat_stream(
                    model="qwen2.5:1.5b",
                    messages=[ChatMessage(role="user", content="Salutations")],
                )
            )
    client.close()


def test_chat_stream_model_not_found_404():
    client = OllamaClient()
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__.return_value = mock_response

    with patch.object(client._client, "stream", return_value=mock_stream_cm):
        with pytest.raises(OllamaModelNotFoundError):
            list(
                client.chat_stream(
                    model="unknown_model",
                    messages=[ChatMessage(role="user", content="Salutations")],
                )
            )
    client.close()


def test_chat_stream_api_error():
    client = OllamaClient()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.is_error = True
    mock_response.text = "Internal Server Error"
    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__.return_value = mock_response

    with patch.object(client._client, "stream", return_value=mock_stream_cm):
        with pytest.raises(OllamaAPIError):
            list(
                client.chat_stream(
                    model="qwen2.5:1.5b",
                    messages=[ChatMessage(role="user", content="Salutations")],
                )
            )
    client.close()


def test_chat_stream_ndjson_model_not_found():
    client = OllamaClient()
    mock_lines = [json.dumps({"error": "model 'mistral' not found, try pulling it first"})]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.iter_lines.return_value = iter(mock_lines)

    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__.return_value = mock_response

    with patch.object(client._client, "stream", return_value=mock_stream_cm):
        with pytest.raises(OllamaModelNotFoundError):
            list(
                client.chat_stream(
                    model="mistral",
                    messages=[ChatMessage(role="user", content="Salut")],
                )
            )
    client.close()


def test_chat_stream_ndjson_generic_error():
    client = OllamaClient()
    mock_lines = [json.dumps({"error": "CUDA out of memory"})]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.iter_lines.return_value = iter(mock_lines)

    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__.return_value = mock_response

    with patch.object(client._client, "stream", return_value=mock_stream_cm):
        with pytest.raises(OllamaAPIError):
            list(
                client.chat_stream(
                    model="qwen2.5:1.5b",
                    messages=[ChatMessage(role="user", content="Salut")],
                )
            )
    client.close()


def test_client_context_manager():
    with OllamaClient() as client:
        assert client is not None
