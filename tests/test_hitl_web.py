import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

_BACKEND_DIR = _ROOT_DIR / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import tools_registry
from routes.conversation_routes import APPROVAL_PATTERN
from src.core.db.database import execute_db_update, get_kingdom_stats, init_database
from src.core.fs_tools import (
    ALLOWED_DIR,
    agent_write_file,
    ask_human_confirmation,
    confirmation_handler,
)
from src.features.tools import default_registry
from tools_registry import (
    CONFIRM_BLOCK_LANG,
    DESTRUCTIVE_TOOLS,
    build_confirm_block,
    create_pending_action,
    run_tool,
    run_tool_confirmed,
    take_pending_action,
)

TEST_FILENAME = "test_hitl_manuscrit.txt"


@pytest.fixture(autouse=True)
def reset_state():
    """Base de données, fichier de test et actions en attente remis à zéro avant et après chaque test."""
    init_database(force_reset=True)
    tools_registry._pending_actions.clear()
    test_file = ALLOWED_DIR / TEST_FILENAME
    if test_file.exists():
        test_file.unlink()
    yield
    tools_registry._pending_actions.clear()
    if test_file.exists():
        test_file.unlink()


def test_console_prompt_is_unchanged_without_handler():
    """Sans handler (CLI), la confirmation passe toujours par input()."""
    with patch("builtins.input", side_effect=["O"]):
        assert ask_human_confirmation("Suppression simulation") is True
    with patch("builtins.input", side_effect=["N"]):
        assert ask_human_confirmation("Suppression simulation") is False


def test_handler_replaces_console_prompt_for_files_and_db():
    summaries = []

    def approve(summary: str) -> bool:
        summaries.append(summary)
        return True

    with patch("builtins.input") as mock_input, confirmation_handler(approve):
        file_res = json.loads(agent_write_file(TEST_FILENAME, "Contenu validé"))
        db_res = json.loads(execute_db_update("UPDATE kingdoms SET ruler = 'Shi Huangdi' WHERE name = 'Qin'"))

    mock_input.assert_not_called()
    assert file_res["status"] == "success"
    assert (ALLOWED_DIR / TEST_FILENAME).read_text(encoding="utf-8") == "Contenu validé"
    assert db_res["status"] == "success"
    assert get_kingdom_stats("Qin")["ruler"] == "Shi Huangdi"
    assert "Créer un nouveau fichier" in summaries[0]
    assert "Exécuter la requête suivante" in summaries[1]


def test_handler_can_reject():
    with confirmation_handler(lambda _summary: False):
        res = json.loads(agent_write_file(TEST_FILENAME, "Doit être rejeté"))
    assert res["status"] == "aborted"
    assert not (ALLOWED_DIR / TEST_FILENAME).exists()


def test_handler_is_scoped_to_its_context():
    """Une fois le bloc terminé, la confirmation redevient interactive."""
    with confirmation_handler(lambda _summary: True):
        pass
    with patch("builtins.input", side_effect=["N"]):
        res = json.loads(agent_write_file(TEST_FILENAME, "Texte"))
    assert res["status"] == "aborted"


def test_destructive_tools_do_not_expose_confirmation_parameters_to_the_llm():
    """Le LLM ne doit pas pouvoir se confirmer lui-même : aucun paramètre de validation dans le schéma."""
    for name in DESTRUCTIVE_TOOLS:
        properties = default_registry.get(name).parameters["properties"]
        assert not {"auto_confirm", "action_id", "callback"} & set(properties)


def test_llm_supplied_auto_confirm_does_not_bypass_confirmation():
    with patch("builtins.input", side_effect=["N"]):
        run_tool("write_manuscript_file", {"filename": TEST_FILENAME, "content": "x", "auto_confirm": True})
    assert not (ALLOWED_DIR / TEST_FILENAME).exists()


def test_run_tool_confirmed_executes_destructive_tool():
    raw = run_tool_confirmed("write_manuscript_file", {"filename": TEST_FILENAME, "content": "Tool test ok"})
    assert json.loads(raw)["status"] == "success"
    assert (ALLOWED_DIR / TEST_FILENAME).exists()


def test_pending_action_is_single_use_and_returns_displayed_args():
    args = {"filename": TEST_FILENAME, "content": "Version affichée"}
    token = create_pending_action("u1", "c1", "write_manuscript_file", args)

    assert take_pending_action(token, "u1", "c1", "write_manuscript_file") == args
    assert take_pending_action(token, "u1", "c1", "write_manuscript_file") is None


@pytest.mark.parametrize("user_id,conv_id,tool", [
    ("autre", "c1", "write_manuscript_file"),
    ("u1", "autre", "write_manuscript_file"),
    ("u1", "c1", "update_kingdom_database"),
])
def test_pending_action_is_bound_to_user_conversation_and_tool(user_id, conv_id, tool):
    token = create_pending_action("u1", "c1", "write_manuscript_file", {"filename": "a", "content": "b"})
    assert take_pending_action(token, user_id, conv_id, tool) is None
    # Un essai invalide ne consomme pas le token légitime
    assert take_pending_action(token, "u1", "c1", "write_manuscript_file") is not None


def test_unknown_or_expired_token_is_rejected():
    assert take_pending_action("act-inconnu", "u1", "c1", "write_manuscript_file") is None

    token = create_pending_action("u1", "c1", "write_manuscript_file", {"filename": "a", "content": "b"})
    user_id, conv_id, tool, args, _expiry = tools_registry._pending_actions[token]
    tools_registry._pending_actions[token] = (user_id, conv_id, tool, args, time.monotonic() - 1)
    assert take_pending_action(token, "u1", "c1", "write_manuscript_file") is None


def test_approval_marker_requires_approval_at_message_start():
    assert APPROVAL_PATTERN.match("[Confirmation : approuvée] [action_id:act-abc_12-X] J'approuve").group(1) == "act-abc_12-X"
    # Un refus porte aussi le token mais ne doit jamais valoir approbation
    assert APPROVAL_PATTERN.match("[Confirmation : refusée] [action_id:act-abc] J'annule") is None
    assert APPROVAL_PATTERN.match("Voici : [Confirmation : approuvée] [action_id:act-abc]") is None
    assert APPROVAL_PATTERN.match("[Confirmation : approuvée] sans token") is None


def test_build_confirm_block_format():
    """Vérifie la génération du bloc sensai-confirm pour l'interface frontend."""
    block = build_confirm_block(
        summary="Écrasement du fichier Fiche_Glace.md",
        tool_name="write_manuscript_file",
        action_id="act-98765",
        details={"filename": "Fiche_Glace.md"},
    )
    assert f"```{CONFIRM_BLOCK_LANG}" in block
    assert "act-98765" in block
    assert "Écrasement du fichier Fiche_Glace.md" in block
