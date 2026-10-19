import json
import pytest
from pydantic import BaseModel, Field

from src.features.structured_output import (
    StructuredOutputError,
    build_retry_correction_message,
    chat_structured_flow,
    generate_json_schema,
    validate_structured_json,
)


class CityInfo(BaseModel):
    name: str = Field(..., description="Nom de la ville")
    population: int = Field(..., ge=0, description="Nombre d'habitants")


def test_generate_json_schema():
    schema = generate_json_schema(CityInfo)
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "population" in schema["properties"]
    assert schema["required"] == ["name", "population"]


def test_validate_structured_json_success():
    raw = json.dumps({"name": "Xianyang", "population": 500000})
    res = validate_structured_json(raw, CityInfo)
    assert isinstance(res, CityInfo)
    assert res.name == "Xianyang"
    assert res.population == 500000


def test_validate_structured_json_failure():
    raw = json.dumps({"name": "Xianyang", "population": -50})
    with pytest.raises(Exception):
        validate_structured_json(raw, CityInfo)


def test_build_retry_correction_message():
    err = ValueError("Champ manquant")
    msg = build_retry_correction_message("raw text", err)
    assert msg["role"] == "user"
    assert "Erreur de validation" in msg["content"]
    assert "Champ manquant" in msg["content"]


def test_chat_structured_flow_success_direct():
    def mock_chat_fn(model: str, messages: list, format: dict):
        return {"message": {"content": json.dumps({"name": "Handan", "population": 300000})}}

    res = chat_structured_flow(
        client_chat_fn=mock_chat_fn,
        model="qwen2.5:1.5b",
        messages=[{"role": "user", "content": "Infos Handan"}],
        response_format=CityInfo,
    )
    assert res.name == "Handan"
    assert res.population == 300000


def test_chat_structured_flow_retry_success():
    calls = 0

    def mock_chat_fn(model: str, messages: list, format: dict):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"message": {"content": "Texte non json"}}
        return {"message": {"content": json.dumps({"name": "Linzi", "population": 400000})}}

    res = chat_structured_flow(
        client_chat_fn=mock_chat_fn,
        model="qwen2.5:1.5b",
        messages=[{"role": "user", "content": "Infos Linzi"}],
        response_format=CityInfo,
        max_retries=1,
    )
    assert calls == 2
    assert res.name == "Linzi"


def test_chat_structured_flow_exhaustion_raises_structured_output_error():
    def mock_chat_fn(model: str, messages: list, format: dict):
        return {"message": {"content": "Toujours invalide"}}

    with pytest.raises(StructuredOutputError) as exc_info:
        chat_structured_flow(
            client_chat_fn=mock_chat_fn,
            model="qwen2.5:1.5b",
            messages=[{"role": "user", "content": "Infos"}],
            response_format=CityInfo,
            max_retries=1,
        )

    assert "Échec de validation" in str(exc_info.value)
    assert exc_info.value.raw_response == "Toujours invalide"
