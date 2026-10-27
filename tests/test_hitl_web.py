import json
import os
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

from src.core.db.database import (
    execute_db_update,
    get_kingdom_stats,
    init_database,
)
from src.core.fs_tools import (
    ALLOWED_DIR,
    agent_read_file,
    agent_write_file,
    ask_human_confirmation,
    clear_action_confirmations,
    is_interactive_terminal,
    register_action_confirmation,
    set_confirmation_callback,
)
from src.features.tools import default_registry
from tools_registry import (
    CONFIRM_BLOCK_LANG,
    DESTRUCTIVE_TOOLS,
    build_confirm_block,
    run_tool,
)


@pytest.fixture(autouse=True)
def cleanup_hitl_state():
    """Réinitialise l'état HITL (callbacks, tokens, DB, fichiers de test) avant et après chaque test."""
    set_confirmation_callback(None)
    clear_action_confirmations()
    if "SENSAI_AUTO_CONFIRM" in os.environ:
        del os.environ["SENSAI_AUTO_CONFIRM"]
    init_database(force_reset=True)

    test_file = ALLOWED_DIR / "test_hitl_manuscrit.txt"
    if test_file.exists():
        test_file.unlink()

    yield

    set_confirmation_callback(None)
    clear_action_confirmations()
    if "SENSAI_AUTO_CONFIRM" in os.environ:
        del os.environ["SENSAI_AUTO_CONFIRM"]
    if test_file.exists():
        test_file.unlink()


def test_fs_non_interactive_does_not_block_and_aborts_by_default():
    """Vérifie qu'en mode non interactif sans approbation, l'écriture fichier ne bloque pas sur stdin et s'annule."""
    test_filename = "test_hitl_manuscrit.txt"

    # En environnement de test, sys.stdin n'est pas un tty
    with patch("src.core.fs_tools.is_interactive_terminal", return_value=False), \
         patch("builtins.input") as mock_input:
        res_raw = agent_write_file(test_filename, "Contenu confidentiel de test")
        res = json.loads(res_raw)

        # Doit refuser sans avoir invoqué input()
        mock_input.assert_not_called()
        assert res.get("status") == "aborted"
        assert "refusé" in res.get("message", "").lower()
        assert not (ALLOWED_DIR / test_filename).exists()


def test_db_non_interactive_does_not_block_and_aborts_by_default():
    """Vérifie qu'en mode non interactif sans approbation, la modification DB ne bloque pas et s'annule."""
    sql = "UPDATE kingdoms SET ruler = 'Usurpateur' WHERE name = 'Qin'"

    with patch("src.core.fs_tools.is_interactive_terminal", return_value=False), \
         patch("builtins.input") as mock_input:
        res_raw = execute_db_update(sql)
        res = json.loads(res_raw)

        mock_input.assert_not_called()
        assert res.get("status") == "aborted"
        # Vérifie que la base de données n'a pas été modifiée
        qin_stats = get_kingdom_stats("Qin")
        assert qin_stats["ruler"] == "Ying Zheng"


def test_auto_confirm_parameter_allows_write_and_update():
    """Vérifie que le paramètre explicite auto_confirm=True permet l'écriture sans bloquer."""
    test_filename = "test_hitl_manuscrit.txt"

    # 1. Écriture fichier avec auto_confirm=True
    res_raw = agent_write_file(test_filename, "Contenu validé", auto_confirm=True)
    res = json.loads(res_raw)
    assert res.get("status") == "success"
    assert (ALLOWED_DIR / test_filename).exists()
    assert (ALLOWED_DIR / test_filename).read_text(encoding="utf-8") == "Contenu validé"

    # 2. Mise à jour DB avec auto_confirm=True
    sql = "UPDATE kingdoms SET ruler = 'Shi Huangdi' WHERE name = 'Qin'"
    db_res_raw = execute_db_update(sql, auto_confirm=True)
    db_res = json.loads(db_res_raw)
    assert db_res.get("status") == "success"
    assert db_res.get("rows_affected") == 1

    qin_stats = get_kingdom_stats("Qin")
    assert qin_stats["ruler"] == "Shi Huangdi"


def test_auto_confirm_parameter_false_aborts():
    """Vérifie que auto_confirm=False rejette l'opération explicitement."""
    test_filename = "test_hitl_manuscrit.txt"
    res_raw = agent_write_file(test_filename, "Doit être rejeté", auto_confirm=False)
    res = json.loads(res_raw)
    assert res.get("status") == "aborted"
    assert not (ALLOWED_DIR / test_filename).exists()


def test_direct_callback_injection():
    """Vérifie l'injection d'un callback d'approbation ou de rejet à l'exécution."""
    test_filename = "test_hitl_manuscrit.txt"
    intercepted_summaries = []

    def approve_callback(summary: str) -> bool:
        intercepted_summaries.append(summary)
        return True

    res_raw = agent_write_file(test_filename, "Par callback approuvé", callback=approve_callback)
    res = json.loads(res_raw)
    assert res.get("status") == "success"
    assert len(intercepted_summaries) == 1
    assert "Créer un nouveau fichier" in intercepted_summaries[0]

    # Test avec un callback rejetant l'écrasement
    def reject_callback(summary: str) -> bool:
        intercepted_summaries.append(summary)
        return False

    res_overwrite = agent_write_file(test_filename, "Nouvelle version", callback=reject_callback)
    res_ow = json.loads(res_overwrite)
    assert res_ow.get("status") == "aborted"
    assert "Écraser le fichier existant" in intercepted_summaries[1]
    # Le fichier d'origine n'a pas été écrasé
    assert (ALLOWED_DIR / test_filename).read_text(encoding="utf-8") == "Par callback approuvé"


def test_global_confirmation_callback():
    """Vérifie qu'un callback global configuré via set_confirmation_callback est bien invoqué."""
    log = []

    set_confirmation_callback(lambda summary: log.append(summary) or True)

    sql = "UPDATE kingdoms SET capital = 'NouvelleXianyang' WHERE name = 'Qin'"
    res_raw = execute_db_update(sql)
    res = json.loads(res_raw)
    assert res.get("status") == "success"
    assert len(log) == 1
    assert "Exécuter la requête suivante" in log[0]


def test_token_action_id_mechanism():
    """Vérifie la confirmation asynchrone par token / action_id pour le backend web."""
    token_approved = "token_act_ok_123"
    token_rejected = "token_act_ko_456"

    register_action_confirmation(token_approved, approved=True)
    register_action_confirmation(token_rejected, approved=False)

    test_filename = "test_hitl_manuscrit.txt"

    # 1. Utilisation du token approuvé
    res_raw1 = agent_write_file(test_filename, "Texte validé par token", action_id=token_approved)
    res1 = json.loads(res_raw1)
    assert res1.get("status") == "success"

    # 2. Utilisation du token refusé
    res_raw2 = agent_write_file(test_filename, "Texte refusé", action_id=token_rejected)
    res2 = json.loads(res_raw2)
    assert res2.get("status") == "aborted"


def test_env_var_sensai_auto_confirm(monkeypatch):
    """Vérifie la prise en compte de la variable d'environnement SENSAI_AUTO_CONFIRM."""
    test_filename = "test_hitl_manuscrit.txt"

    # Test valeur positive
    monkeypatch.setenv("SENSAI_AUTO_CONFIRM", "1")
    res1 = json.loads(agent_write_file(test_filename, "Texte auto-confirmé via env"))
    assert res1.get("status") == "success"

    # Test valeur négative
    monkeypatch.setenv("SENSAI_AUTO_CONFIRM", "0")
    res2 = json.loads(agent_write_file(test_filename, "Texte rejeté via env"))
    assert res2.get("status") == "aborted"


def test_cli_interactive_tty_fallback():
    """Vérifie que si un TTY interactif est détecté (mode CLI), input() est bien appelé en fallback."""
    with patch("src.core.fs_tools.is_interactive_terminal", return_value=True), \
         patch("builtins.input", side_effect=["O"]):
        res = ask_human_confirmation("Suppression simulation")
        assert res is True

    with patch("src.core.fs_tools.is_interactive_terminal", return_value=True), \
         patch("builtins.input", side_effect=["N"]):
        res = ask_human_confirmation("Suppression simulation")
        assert res is False


def test_tool_registry_write_and_update_with_hitl():
    """Vérifie que les outils du registre partagé (write_manuscript_file et update_kingdom_database) supportent HITL."""
    assert "write_manuscript_file" in DESTRUCTIVE_TOOLS
    assert "update_kingdom_database" in DESTRUCTIVE_TOOLS

    test_filename = "test_hitl_manuscrit.txt"

    # 1. Exécution via ToolExecutor sans auto_confirm (doit s'annuler proprement sans bloquer)
    with patch("src.core.fs_tools.is_interactive_terminal", return_value=False):
        raw_res = run_tool("write_manuscript_file", {"filename": test_filename, "content": "Tool test"})
        parsed = json.loads(raw_res)
        assert parsed.get("status") == "aborted"

    # 2. Exécution via ToolExecutor avec auto_confirm=True
    raw_res_ok = run_tool(
        "write_manuscript_file",
        {"filename": test_filename, "content": "Tool test ok", "auto_confirm": True},
    )
    parsed_ok = json.loads(raw_res_ok)
    assert parsed_ok.get("status") == "success"
    assert (ALLOWED_DIR / test_filename).exists()


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
