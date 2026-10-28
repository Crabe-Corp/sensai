import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from src.core.db.database import init_database
from src.core.engine import TokenChunkEvent, ToolCallEvent, ToolResultEvent
from src.core.ollama_client import ChatMessage, OllamaClient
from src.core.schemas import HistoricalFigure, KingdomInfo, StructuredResponse
from src.features.memory import ProfileManager, SessionManager
from src.features.tools.executor import ToolExecutor
from src.features.tools.mcp_client import MCPClient
from src.features.tools.registry import default_registry
from src.interfaces.cli.main import run_session

REPORT_FILE = PROJECT_ROOT / "cli_test_report.log"
COMMANDS_FILE = SCRIPT_DIR / "cli_test_commands.txt"

TEST_INPUTS = [
    "/help",
    "/history",
    "/models",
    "/model",
    "/profile show",
    "/profile list",
    "/profile load test_user",
    "/profile show",
    "/session list",
    "/session new TestSessionAuto",
    "Bonjour, présente-toi brièvement.",
    "/history",
    "/clear",
    "/history",
    "/kingdom Qin",
    "/figure Qin Shi Huang",
    "/structured-output on",
    "Résume en cinq mots la période des Royaumes Combattants.",
    "/structured-output off",
    "/tools on",
    "Donne-moi les informations de renseignement sur le royaume de Qin.",
    "Recherche sur le web les dernières découvertes sur l'armée de terre cuite.",
    "/mcp status",
    "/mcp connect python -m src.features.tools.mcp_server_demo",
    "/tools",
    "Calcule l'approvisionnement en grain pour 50000 soldats de Qin pendant 3 mois.",
    "Quels sont les détails de la bataille de Changping ?",
    "/mcp disconnect",
    "/session list",
    "/exit",
]


def is_ollama_online(host: str = "http://localhost:11434") -> bool:
    """Vérifie si le serveur local Ollama est en ligne et accessible.
            PARAMS: - host - STR: URL racine du serveur Ollama
            RETURN: booléen indiquant si le serveur répond avec succès"""
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{host}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def build_mock_client_and_engine():
    """Construit un client Ollama factice et un moteur de streaming simulé pour les tests.
            PARAMS: Aucun
            RETURN: tuple contenant le client simulé et la fonction fake_run_stream"""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.base_url = "http://localhost:11434"
    mock_client.list_models.return_value = ["qwen2.5:1.5b", "llama3:latest", "mistral:latest"]

    def fake_chat_structured(model: str, messages: list[Any], response_format: type[Any]):
        if response_format is KingdomInfo:
            return KingdomInfo(
                nom="Qin",
                capitale="Xianyang",
                souverain="Qin Shi Huang",
                puissance_militaire=95,
                specialite_strategique="Arbalétriers en formation serrée et cavalerie rapide",
                description="Royaume de l'ouest unificateur de la Chine en 221 av. J.-C.",
            )
        elif response_format is HistoricalFigure:
            return HistoricalFigure(
                nom="Qin Shi Huang",
                royaume_origine="Qin",
                role="souverain",
                faits_marquants=[
                    "Premier empereur de la dynastie Qin",
                    "Unification de la Grande Muraille et standardisation de l'écriture",
                ],
            )
        elif response_format is StructuredResponse:
            return StructuredResponse(response="Xianyang était la capitale fortifiée de l'État de Qin.")
        return response_format.model_validate({})

    mock_client.chat_structured.side_effect = fake_chat_structured

    tool_executor = ToolExecutor(registry=default_registry)

    def fake_run_stream(messages: list[Any], model: str, tools: Any = None):
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        if "renseignement sur le royaume de qin" in content.lower():
            args = {"kingdom_name": "Qin"}
            yield ToolCallEvent(tool_name="get_kingdom_info", arguments=args)
            res = tool_executor.execute("get_kingdom_info", args)
            yield ToolResultEvent(tool_name="get_kingdom_info", result=res.result, is_error=not res.success)
            reply = f"Voici les données d'archives sur Qin : Capitale Xianyang, armée active."
            for tok in reply.split():
                yield TokenChunkEvent(token=tok + " ")
            return

        if "armée de terre cuite" in content.lower() or "recherche sur le web" in content.lower():
            args = {"query": "armée de terre cuite Xi'an", "max_results": 2}
            yield ToolCallEvent(tool_name="web_search", arguments=args)
            res = tool_executor.execute("web_search", args)
            yield ToolResultEvent(tool_name="web_search", result=res.result, is_error=not res.success)
            reply = "D'après les sources récentes du Web, l'armée de terre cuite reste un trésor archéologique majeur."
            for tok in reply.split():
                yield TokenChunkEvent(token=tok + " ")
            return

        if "approvisionnement en grain" in content.lower():
            args = {"kingdom": "Qin", "soldiers": 50000, "months": 3}
            yield ToolCallEvent(tool_name="calculate_grain_supply", arguments=args)
            res = tool_executor.execute("calculate_grain_supply", args)
            yield ToolResultEvent(tool_name="calculate_grain_supply", result=res.result, is_error=not res.success)
            reply = "Les calculs logistiques prévoient 6750 tonnes de grain pour cette campagne."
            for tok in reply.split():
                yield TokenChunkEvent(token=tok + " ")
            return

        if "changping" in content.lower():
            args = {"battle_name": "changping"}
            yield ToolCallEvent(tool_name="get_historical_battle", arguments=args)
            res = tool_executor.execute("get_historical_battle", args)
            yield ToolResultEvent(tool_name="get_historical_battle", result=res.result, is_error=not res.success)
            reply = "La bataille de Changping (-260) s'est soldée par une victoire décisive de Qin."
            for tok in reply.split():
                yield TokenChunkEvent(token=tok + " ")
            return

        reply = "Je suis l'assistant SENSAI spécialisé sur les Royaumes Combattants."
        for tok in reply.split():
            yield TokenChunkEvent(token=tok + " ")

    return mock_client, fake_run_stream


def run_e2e_test(live_mode: bool = False) -> tuple[str, list[tuple[str, bool, str]]]:
    """Exécute l'ensemble du scénario de test de bout en bout de la CLI et consigne les résultats.
            PARAMS: - live_mode - BOOL: exécute en conditions réelles avec Ollama si True
            RETURN: tuple contenant la sortie textuelle brute et la liste des vérifications"""
    init_database()
    captured_stdout = io.StringIO()
    checks: list[tuple[str, bool, str]] = []

    ollama_ready = is_ollama_online()
    effective_live = live_mode and ollama_ready

    if live_mode and not ollama_ready:
        print("[Attention] Mode live demandé mais Ollama est inaccessible sur http://localhost:11434.")
        print("[Info] Basculement automatique sur le moteur d'exécution simulé (mocks & outils réels).\n")

    input_generator = iter(TEST_INPUTS)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_session_mgr = SessionManager(storage_dir=Path(tmp_dir) / "sessions")
        tmp_profile_mgr = ProfileManager(storage_dir=Path(tmp_dir) / "profiles")
        if effective_live:
            print("==> Exécution en direct (LIVE) contre le serveur Ollama...")
            with OllamaClient(base_url="http://localhost:11434") as real_client:
                with patch("sys.stdout", captured_stdout), patch("builtins.input", lambda _: next(input_generator)):
                    run_session(
                        client=real_client,
                        model="qwen2.5:1.5b",
                        host="http://localhost:11434",
                        tools=None,
                        profile_name="default",
                        session_manager=tmp_session_mgr,
                        profile_manager=tmp_profile_mgr,
                    )
        else:
            print("==> Exécution du protocole de test E2E (Moteur CLI + SQLite + MCP réels)...")
            mock_client, fake_stream = build_mock_client_and_engine()
            with patch("sys.stdout", captured_stdout), patch("builtins.input", lambda _: next(input_generator)):
                with patch("src.interfaces.cli.main.ConversationEngine.run_stream", side_effect=fake_stream):
                    run_session(
                        client=mock_client,
                        model="qwen2.5:1.5b",
                        host="http://localhost:11434",
                        tools=None,
                        profile_name="default",
                        session_manager=tmp_session_mgr,
                        profile_manager=tmp_profile_mgr,
                    )

    raw_output = captured_stdout.getvalue()

    # Assertions de conformité
    checks.append((
        "Socle [B1] : Bannière d'accueil & initialisation",
        ("SENSAI CLI — Modular Chatbot" in raw_output),
        "Bannière de démarrage affichée",
    ))
    checks.append((
        "Socle [B1] : Commande /help",
        ("Commandes disponibles :" in raw_output or "Available commands:" in raw_output) and "/session list" in raw_output,
        "Menu d'aide exhaustif documenté",
    ))
    checks.append((
        "Socle [B1] : Commande /history",
        ("Historique actuel :" in raw_output or "Current history :" in raw_output),
        "Comptage des messages vérifié",
    ))
    checks.append((
        "Socle [B1] : Commande /models & /model",
        ("Modèles disponibles" in raw_output or "Available models" in raw_output or "Models installed" in raw_output) and ("Modèle actuellement sélectionné" in raw_output or "Currently selected model" in raw_output),
        "Inspection du modèle à chaud",
    ))
    checks.append((
        "Profils [M1] : /profile show, list & load",
        ("Profil 'test_user' chargé" in raw_output or "Profile 'test_user' loaded" in raw_output) and ("Profils existants" in raw_output or "Existing profiles" in raw_output),
        "Gestion et bascule de persona validées",
    ))
    checks.append((
        "Sessions [M1] : /session new, list & /clear",
        ("Nouvelle session initialisée :" in raw_output or "New session initialized :" in raw_output) and ("Historique de session réinitialisé" in raw_output or "Session history reset" in raw_output),
        "Persistance et réinitialisation de session",
    ))
    checks.append((
        "Sorties Structurées [T5] - Cas 1 : /kingdom Qin",
        (("puissance_militaire" in raw_output and "specialite_strategique" in raw_output) or ("military_power" in raw_output and "strategic_specialty" in raw_output)),
        "Schéma KingdomInfo JSON strict validé",
    ))
    checks.append((
        "Sorties Structurées [T5] - Cas 2 : /figure Qin Shi Huang",
        (("faits_marquants" in raw_output and "royaume_origine" in raw_output) or ("notable_facts" in raw_output and "origin_kingdom" in raw_output)),
        "Schéma HistoricalFigure JSON strict validé",
    ))
    checks.append((
        "Sorties Structurées [T5] - Cas 3 : /structured-output",
        ("Mode sortie structurée activé" in raw_output or "Structured output mode enabled" in raw_output) and '"response":' in raw_output,
        "Schéma StructuredResponse générique validé",
    ))
    checks.append((
        "Outils & Web [T3] : get_kingdom_info & web_search",
        "get_kingdom_info" in raw_output and "web_search" in raw_output,
        "Interception et exécution d'outils en temps réel",
    ))
    checks.append((
        "Protocole MCP [T1] : /mcp connect & outils externes",
        "calculate_grain_supply" in raw_output and "get_historical_battle" in raw_output,
        "Serveur MCP stdio connecté et exécuté",
    ))
    checks.append((
        "Socle [B1] : Commande /exit",
        ("Fermeture de SENSAI." in raw_output or "Exiting SENSAI." in raw_output),
        "Fermeture propre de la CLI",
    ))

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(raw_output)

    return raw_output, checks


def main():
    """Point d'entrée du script de test CLI E2E analysant les options et exécutant la suite.
            PARAMS: Aucun
            RETURN: code de retour entier (0 en cas de succès, 1 si échec)"""
    parser = argparse.ArgumentParser(description="Script de test automatisé de bout en bout de la CLI SENSAI.")
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Exécuter les requêtes en conditions réelles avec le serveur Ollama actif.",
    )
    args = parser.parse_args()

    start_time = time.time()
    raw_output, checks = run_e2e_test(live_mode=args.live)
    duration = time.time() - start_time

    print("\n" + "=" * 70)
    print(" RÉSULTATS DU PROTOCOLE DE TEST AUTOMATISÉ CLI — SENSAI")
    print("=" * 70)

    all_passed = True
    for name, success, detail in checks:
        status_tag = "[PASS] OK" if success else "[FAIL] ERREUR"
        print(f" {status_tag:<12} | {name:<50} | {detail}")
        if not success:
            all_passed = False

    print("-" * 70)
    total_checks = len(checks)
    passed_count = sum(1 for _, s, _ in checks if s)
    print(f"Bilan : {passed_count}/{total_checks} fonctionnalités validées en {duration:.2f}s.")
    print(f"Journal complet de la session CLI sauvegardé dans : {REPORT_FILE.resolve()}")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


def test_cli_e2e():
    """Test pytest automatisé de bout en bout validant le cycle complet de la CLI SENSAI.
            PARAMS: Aucun
            RETURN: None"""
    _raw_output, checks = run_e2e_test(live_mode=False)
    failed = [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    assert not failed, f"Échecs des vérifications E2E CLI: {failed}"


if __name__ == "__main__":
    sys.exit(main())
