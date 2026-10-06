import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from src.cli.main import run_session
from src.core.ollama_client import (
    ChatMessage,
    OllamaAPIError,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStructuredOutputError,
)
from src.core.schemas import HistoricalFigure, KingdomInfo


def test_kingdom_info_validation():
    valid_data = {
        "nom": "Qin",
        "capitale": "Xianyang",
        "souverain": "Ying Zheng",
        "puissance_militaire": 95,
        "specialite_strategique": "Infanterie lourde et arbalétriers",
        "description": "Royaume martial réformé par le légisme, futur unificateur.",
    }
    kingdom = KingdomInfo.model_validate(valid_data)
    assert kingdom.nom == "Qin"
    assert kingdom.name == "Qin"
    assert kingdom.capitale == "Xianyang"
    assert kingdom.capital == "Xianyang"
    assert kingdom.souverain == "Ying Zheng"
    assert kingdom.ruler == "Ying Zheng"
    assert kingdom.puissance_militaire == 95
    assert kingdom.military_power == 95
    assert kingdom.strategic_specialty == "Infanterie lourde et arbalétriers"


def test_kingdom_info_aliases_and_boundaries():
    english_data = {
        "name": "Zhao",
        "capital": "Handan",
        "ruler": "Roi Wuling",
        "military_power": 88,
        "strategic_specialty": "Archers montés",
        "description": "Royaume réputé pour sa puissante cavalerie nomade.",
    }
    kingdom = KingdomInfo.model_validate(english_data)
    assert kingdom.nom == "Zhao"
    assert kingdom.puissance_militaire == 88

    with pytest.raises(ValidationError):
        KingdomInfo.model_validate({**english_data, "military_power": 150})

    with pytest.raises(ValidationError):
        KingdomInfo.model_validate({**english_data, "military_power": 0})


def test_historical_figure_validation_and_normalization():
    data = {
        "nom": "Bai Qi",
        "royaume_origine": "Qin",
        "role": "general",
        "faits_marquants": ["Victoire écrasante à Changping", "Commandant invaincu"],
    }
    figure = HistoricalFigure.model_validate(data)
    assert figure.nom == "Bai Qi"
    assert figure.name == "Bai Qi"
    assert figure.role == "général"
    assert figure.origin_kingdom == "Qin"
    assert len(figure.facts) == 2


def test_historical_figure_invalid_role():
    data = {
        "nom": "Inconnu",
        "royaume_origine": "Qin",
        "role": "paysan",
        "faits_marquants": [],
    }
    with pytest.raises(ValidationError):
        HistoricalFigure.model_validate(data)


def test_chat_non_stream_success():
    client = OllamaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "message": {"role": "assistant", "content": '{"nom": "Qin"}'}
    }

    with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
        result = client.chat(
            model="qwen2.5:1.5b",
            messages=[ChatMessage(role="user", content="Infos Qin")],
            format="json",
        )
        assert result["message"]["content"] == '{"nom": "Qin"}'

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["model"] == "qwen2.5:1.5b"
        assert payload["stream"] is False
        assert payload["format"] == "json"
        assert payload["messages"] == [{"role": "user", "content": "Infos Qin"}]

    client.close()


def test_chat_structured_schema_transmission_and_success():
    client = OllamaClient()
    expected_schema = KingdomInfo.model_json_schema()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "nom": "Qin",
                    "capitale": "Xianyang",
                    "souverain": "Ying Zheng",
                    "puissance_militaire": 98,
                    "specialite_strategique": "Réforme légiste et arbalètes",
                    "description": "État centralisé et martial.",
                }
            ),
        }
    }

    with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
        result = client.chat_structured(
            model="qwen2.5:1.5b",
            messages=[ChatMessage(role="user", content="Décris Qin")],
            response_format=KingdomInfo,
        )

        assert isinstance(result, KingdomInfo)
        assert result.nom == "Qin"
        assert result.puissance_militaire == 98

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["format"] == expected_schema
        assert payload["stream"] is False

    client.close()


def test_chat_structured_retry_mechanism_success():
    client = OllamaClient()

    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.is_error = False
    bad_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "Ceci n'est pas un JSON valide mais du texte libre.",
        }
    }

    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.is_error = False
    good_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "nom": "Shang Yang",
                    "royaume_origine": "Wei",
                    "role": "légiste",
                    "faits_marquants": ["Réformes institutionnelles de Qin"],
                }
            ),
        }
    }

    with patch.object(client._client, "post", side_effect=[bad_resp, good_resp]) as mock_post:
        result = client.chat_structured(
            model="qwen2.5:1.5b",
            messages=[ChatMessage(role="user", content="Fiche Shang Yang")],
            response_format=HistoricalFigure,
            max_retries=1,
        )

        assert isinstance(result, HistoricalFigure)
        assert result.nom == "Shang Yang"
        assert result.role == "légiste"
        assert mock_post.call_count == 2
        second_payload = mock_post.call_args_list[1][1]["json"]
        messages = second_payload["messages"]
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert "texte libre" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Erreur de validation" in messages[2]["content"]

    client.close()


def test_chat_structured_retries_exhausted_raises_exception():
    client = OllamaClient()

    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.is_error = False
    bad_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": '{"nom": "Invalide", "puissance_militaire": 999}',
        }
    }

    with patch.object(client._client, "post", return_value=bad_resp) as mock_post:
        with pytest.raises(OllamaStructuredOutputError) as exc_info:
            client.chat_structured(
                model="qwen2.5:1.5b",
                messages=[ChatMessage(role="user", content="Génère un royaume")],
                response_format=KingdomInfo,
                max_retries=1,
            )

        assert "Échec de validation" in str(exc_info.value)
        assert exc_info.value.raw_response is not None
        assert exc_info.value.validation_error is not None
        assert mock_post.call_count == 2

    client.close()


def test_chat_structured_zero_retries_fails_immediately():
    client = OllamaClient()

    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.is_error = False
    bad_resp.json.return_value = {
        "message": {"role": "assistant", "content": "Pas de json"}
    }

    with patch.object(client._client, "post", return_value=bad_resp) as mock_post:
        with pytest.raises(OllamaStructuredOutputError):
            client.chat_structured(
                model="qwen2.5:1.5b",
                messages=[ChatMessage(role="user", content="Test")],
                response_format=KingdomInfo,
                max_retries=0,
            )

        assert mock_post.call_count == 1

    client.close()


def test_chat_errors_passthrough():
    client = OllamaClient()

    with patch.object(client._client, "post", side_effect=httpx.ConnectError("Offline")):
        with pytest.raises(OllamaConnectionError):
            client.chat("qwen2.5:1.5b", [{"role": "user", "content": "Hello"}])

    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.is_error = True
    with patch.object(client._client, "post", return_value=mock_404):
        with pytest.raises(OllamaModelNotFoundError):
            client.chat("unknown", [{"role": "user", "content": "Hello"}])

    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.is_error = True
    mock_500.text = "Internal error"
    with patch.object(client._client, "post", return_value=mock_500):
        with pytest.raises(OllamaAPIError):
            client.chat("qwen2.5:1.5b", [{"role": "user", "content": "Hello"}])

    client.close()


def test_cli_kingdom_and_figure_commands(capsys):
    mock_client = MagicMock()
    mock_client.chat_structured.side_effect = [
        KingdomInfo(
            nom="Qin",
            capitale="Xianyang",
            souverain="Ying Zheng",
            puissance_militaire=95,
            specialite_strategique="Arbalétriers",
            description="État unificateur.",
        ),
        HistoricalFigure(
            nom="Li Si",
            royaume_origine="Chu",
            role="légiste",
            faits_marquants=["Chancelier de Qin", "Standardisation de l'écriture"],
        ),
    ]

    with patch(
        "builtins.input",
        side_effect=["/kingdom Qin", "/figure Li Si", "/exit"],
    ):
        exit_code = run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")
        assert exit_code is None

    assert mock_client.chat_structured.call_count == 2
    captured = capsys.readouterr()
    assert "Xianyang" in captured.out
    assert "Standardisation de l'écriture" in captured.out


def test_cli_kingdom_structured_error_handling(capsys):
    mock_client = MagicMock()
    mock_client.chat_structured.side_effect = OllamaStructuredOutputError("Format non respecté")

    with patch("builtins.input", side_effect=["/kingdom Han", "/exit"]):
        exit_code = run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434")
        assert exit_code is None

    mock_client.chat_structured.assert_called_once()
    captured = capsys.readouterr()
    assert "[Erreur Sortie Structurée] Format non respecté" in captured.out
