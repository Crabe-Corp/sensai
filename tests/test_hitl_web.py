import sys
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
from src.features.simulation.human_verif import confirm_simple
from src.features.simulation.tools import simulation_registry
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


@pytest.fixture(autouse=True)
def reset_state():
    """Actions en attente remises à zéro avant et après chaque test."""
    tools_registry._pending_actions.clear()
    yield
    tools_registry._pending_actions.clear()


def test_console_prompt_is_unchanged_without_handler():
    """Sans handler (CLI), la confirmation passe toujours par input()."""
    with patch("builtins.input", side_effect=["Y"]):
        assert confirm_simple("Suppression simulation") is True
    with patch("builtins.input", side_effect=["N"]):
        assert confirm_simple("Suppression simulation") is False


def test_destructive_tools_do_not_expose_confirmation_parameters_to_the_llm():
    """Le LLM ne doit pas pouvoir se confirmer lui-même : aucun paramètre de validation dans le schéma."""
    for name in DESTRUCTIVE_TOOLS:
        tool_def = default_registry.get(name) or simulation_registry.get(name)
        assert tool_def is not None
        properties = tool_def.parameters["properties"]
        assert not {"auto_confirm", "action_id", "callback"} & set(properties)


def test_approval_marker_requires_approval_at_message_start():
    assert APPROVAL_PATTERN.match("[Confirmation : approuvée] [action_id:act-abc_12-X] J'approuve").group(1) == "act-abc_12-X"
    # Un refus porte aussi le token mais ne doit jamais valoir approbation
    assert APPROVAL_PATTERN.match("[Confirmation : refusée] [action_id:act-abc] J'annule") is None
    assert APPROVAL_PATTERN.match("Voici : [Confirmation : approuvée] [action_id:act-abc]") is None
    assert APPROVAL_PATTERN.match("[Confirmation : approuvée] sans token") is None
