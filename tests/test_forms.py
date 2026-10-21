import json

import pytest

from src.features.tools import forms
from src.features.tools.executor import ToolExecutor
from src.features.tools.registry import default_registry


def test_ask_user_form_is_registered_with_schema():
    tool_def = default_registry.get("ask_user_form")
    assert tool_def is not None
    assert set(tool_def.parameters["required"]) == {"title", "questions"}


def test_normalize_form_applies_defaults_and_aliases():
    form = forms.normalize_form(
        "Profil",
        [
            {"label": "Âge ?", "type": "int"},
            "Ville",
            {"label": "Couleur", "type": "select", "options": ["rouge", "bleu"], "required": False},
        ],
    )
    assert form["title"] == "Profil"
    assert [q["id"] for q in form["questions"]] == ["age", "ville", "couleur"]
    assert [q["type"] for q in form["questions"]] == ["number", "text", "choice"]
    assert form["questions"][2]["required"] is False


def test_normalize_form_accepts_json_string_and_default_title():
    form = forms.normalize_form("", json.dumps([{"label": "Nom"}]))
    assert form["title"] == "Informations requises"
    assert form["questions"][0]["id"] == "nom"


def test_normalize_form_makes_ids_unique():
    form = forms.normalize_form("T", [{"label": "Nom"}, {"label": "Nom"}])
    ids = [q["id"] for q in form["questions"]]
    assert len(set(ids)) == 2


@pytest.mark.parametrize(
    "questions",
    [
        [],
        "pas du json",
        [{"type": "text"}],
        [{"label": "A", "type": "inconnu"}],
        [{"label": "A", "type": "choice", "options": ["seul"]}],
        [{"label": f"Q{i}"} for i in range(forms.MAX_QUESTIONS + 1)],
    ],
)
def test_normalize_form_rejects_invalid(questions):
    with pytest.raises(ValueError):
        forms.normalize_form("T", questions)


def test_cli_form_collects_typed_answers(monkeypatch):
    replies = iter(["", "Bob", "42", "o", "2"])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    result = ToolExecutor().execute(
        "ask_user_form",
        {
            "title": "Profil",
            "questions": [
                {"label": "Nom", "type": "text"},
                {"label": "Âge", "type": "number"},
                {"label": "Majeur", "type": "boolean"},
                {"label": "Camp", "type": "choice", "options": ["Qin", "Chu"]},
            ],
        },
    )
    assert result.success
    assert result.result == {
        "status": "answered",
        "answers": {"nom": "Bob", "age": 42, "majeur": True, "camp": "Chu"},
    }


def test_cli_form_cancelled_on_eof(monkeypatch):
    def raise_eof(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    result = forms.ask_user_form("T", [{"label": "Nom"}])
    assert result == {"status": "cancelled"}


def test_cli_form_reports_invalid_description():
    result = forms.ask_user_form("T", [])
    assert result["status"] == "error"
