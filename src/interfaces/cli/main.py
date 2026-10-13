import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from src.core.db.database import init_database
from src.core.engine import (
    ConversationEngine,
    EngineEvent,
    ErrorEvent,
    TokenChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from src.core.ollama_client import (
    ChatMessage,
    OllamaAPIError,
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaStructuredOutputError,
)
from src.core.schemas import HistoricalFigure, KingdomInfo, StructuredResponse
from src.features.tools import builtin
from src.features.tools.mcp_client import MCPClient, MCPError
from src.features.tools.registry import default_registry

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"


def load_config_file(config_path: Path) -> dict[str, Any]:
    """Charge et lit le fichier de configuration JSON s'il existe sur le disque.
            PARAMS: - config_path - PATH: chemin vers le fichier de configuration JSON
            RETURN: dictionnaire contenant la configuration lue ou dictionnaire vide"""
    if not config_path.is_file():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_configuration(cli_args: argparse.Namespace) -> tuple[str, str]:
    """Détermine l'hôte et le modèle Ollama en combinant CLI, variables d'environnement et config.
            PARAMS: - cli_args - NAMESPACE: arguments analysés de la ligne de commande
            RETURN: tuple contenant l'URL de l'hôte et le nom du modèle sélectionnés"""
    file_cfg = load_config_file(Path(cli_args.config)) if cli_args.config else {}

    host = (
        cli_args.host
        or os.getenv("SENSAI_HOST")
        or os.getenv("OLLAMA_HOST")
        or file_cfg.get("ollama_host")
        or DEFAULT_HOST
    )
    model = (
        cli_args.model
        or os.getenv("SENSAI_MODEL")
        or os.getenv("OLLAMA_MODEL")
        or file_cfg.get("default_model")
        or DEFAULT_MODEL
    )
    return host, model


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de ligne de commande passés au programme.
            PARAMS: - argv - LIST[STR] | NONE: arguments de ligne de commande optionnels
            RETURN: objet Namespace contenant les arguments analysés"""
    parser = argparse.ArgumentParser(
        prog="sensai",
        description="SENSAI CLI — Chatbot conversationnel connecté à Ollama en local.",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Nom du modèle Ollama à utiliser (ex: qwen2.5:1.5b, llama3, mistral).",
    )
    parser.add_argument(
        "-H",
        "--host",
        type=str,
        default=None,
        help="URL du serveur Ollama (défaut: http://localhost:11434).",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.json",
        help="Chemin vers le fichier de configuration JSON.",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        default=False,
        help="Activer le support des outils MCP.",
    )
    parser.add_argument(
        "--mcp-server",
        type=str,
        default=None,
        help="Commande pour lancer un serveur MCP externe (ex: 'python -m src.features.tools.mcp_server_demo').",
    )
    return parser.parse_args(argv)


def print_banner(model: str, host: str, tools_enabled: bool = False) -> None:
    """Affiche la bannière d'accueil de la CLI avec les paramètres de connexion actifs.
            PARAMS: - model - STR: nom du modèle Ollama en cours d'utilisation
                    - host - STR: URL du serveur Ollama
                    - tools_enabled - BOOL: indicateur d'activation du support des outils
            RETURN: None"""
    print("=" * 60)
    print(" SENSAI CLI — Chatbot Modulaire")
    print(f" Modèle actif : {model}")
    print(f" Hôte Ollama  : {host}")
    print(f" Outils MCP   : {'Activés' if tools_enabled else 'Désactivés'}")
    print(" Tapez '/help' pour voir les commandes ou '/exit' pour quitter.")
    print("=" * 60)


def print_help() -> None:
    """Affiche dans la console l'ensemble des commandes spéciales disponibles dans la session.
            PARAMS: Aucun
            RETURN: None"""
    print("\nCommandes disponibles :")
    print("  /help                     : Affiche ce message d'aide")
    print("  /clear                    : Réinitialise l'historique de la session")
    print("  /history                  : Affiche le nombre de messages échangés")
    print("  /models                   : Liste les modèles installés sur le serveur Ollama")
    print("  /model [nom]              : Affiche ou change le modèle actif sans redémarrer")
    print("  /tools [on|off]           : Liste les outils disponibles ou active/désactive les outils")
    print("  /mcp [status|connect|disconnect] : Gère la connexion à un serveur MCP externe")
    print("  /kingdom [nom]            : Génère une fiche de royaume au format JSON strict")
    print("  /figure [nom]             : Génère une fiche de personnage historique")
    print("  /structured-output [msg]  : Active/désactive le mode JSON ou soumet une requête")
    print("  /exit | /quit             : Quitte l'application\n")


def run_session(
    client: OllamaClient,
    model: str,
    host: str,
    tools: Any = None,
    mcp_server_cmd: str | None = None,
) -> None:
    """Gère la boucle interactive du chatbot CLI, l'historique et les commandes slash.
            PARAMS: - client - OLLAMACLIENT: instance active du client HTTP Ollama
                    - model - STR: nom du modèle Ollama à utiliser
                    - host - STR: URL du serveur Ollama
                    - tools - ANY: registre ou outils optionnels à exposer au LLM
                    - mcp_server_cmd - STR | NONE: commande de démarrage d'un serveur MCP externe
            RETURN: None"""
    history: list[ChatMessage] = []
    structured_mode: bool = False
    active_tools = tools
    tools_enabled = active_tools is not None
    mcp_client: MCPClient | None = None
    mcp_tool_names: list[str] = []

    if mcp_server_cmd:
        try:
            mcp_client = MCPClient(mcp_server_cmd)
            mcp_client.start()
            mcp_defs = default_registry.register_mcp_client(mcp_client)
            mcp_tool_names = [d.name for d in mcp_defs]
            active_tools = default_registry
            tools_enabled = True
            print(f"[Info] Serveur MCP démarré ({mcp_server_cmd}). {len(mcp_defs)} outil(s) chargé(s).")
        except Exception as exc:
            print(f"[Avertissement MCP] Échec de connexion au serveur MCP : {exc}")

    print_banner(model, host, tools_enabled=tools_enabled)
    init_database()
    engine = ConversationEngine(client=client, registry=default_registry)

    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession interrompue.")
            break

        if not user_input:
            print("[Info] Veuillez saisir un message non vide.")
            continue

        if user_input in ("/exit", "/quit"):
            print("Fermeture de SENSAI.")
            break

        if user_input == "/clear":
            history.clear()
            print("[Info] Historique de session réinitialisé.")
            continue

        if user_input == "/history":
            print(f"[Info] Historique actuel : {len(history)} message(s) en mémoire.")
            continue

        if user_input == "/help":
            print_help()
            continue

        if user_input == "/models":
            try:
                models = client.list_models()
                print(f"[Info] Modèles disponibles ({len(models)}) : {', '.join(models) if models else 'Aucun'}")
            except OllamaError as err:
                print(f"[Erreur] {err}")
            continue

        if user_input == "/model" or user_input.startswith("/model "):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                model = parts[1].strip()
                print(f"[Info] Modèle actif modifié : {model}")
            else:
                print(f"[Info] Modèle actuellement sélectionné : {model}")
                print("[Astuce] Pour changer : /model <nom_du_modèle> (ex: /model llama3)")
            continue

        if user_input == "/tools" or user_input.startswith("/tools "):
            parts = user_input.split(maxsplit=1)
            sub = parts[1].strip().lower() if len(parts) > 1 else ""
            if sub in ("on", "1", "enable", "activer"):
                active_tools = default_registry
                print("[Info] Outils MCP activés pour cette session.")
            elif sub in ("off", "0", "disable", "desactiver", "désactiver"):
                active_tools = None
                print("[Info] Outils MCP désactivés pour cette session.")
            else:
                registered = default_registry.list_tools()
                print(f"[Info] Outils enregistrés ({len(registered)}) :")
                for t in registered:
                    print(f"  - {t.name}: {t.description}")
                print(f"[Info] Statut actuel : {'Activés' if active_tools is not None else 'Désactivés'}")
            continue

        if user_input == "/mcp" or user_input.startswith("/mcp "):
            parts = user_input.split(maxsplit=2)
            subcmd = parts[1].strip().lower() if len(parts) > 1 else "status"
            if subcmd == "status":
                if mcp_client and mcp_client.is_connected:
                    tools = mcp_client.list_tools()
                    print(f"[Info] Serveur MCP connecté : {' '.join(mcp_client.command)}")
                    print(f"[Info] Outils MCP exposés ({len(tools)}) : {', '.join(t.name for t in tools)}")
                else:
                    print("[Info] Aucun serveur MCP externe connecté.")
            elif subcmd == "connect":
                if len(parts) < 3 or not parts[2].strip():
                    print("[Info] Usage : /mcp connect <commande_serveur> (ex: /mcp connect python -m src.features.tools.mcp_server_demo)")
                else:
                    cmd_str = parts[2].strip()
                    try:
                        if mcp_client:
                            default_registry.unregister_tools(mcp_tool_names)
                            mcp_client.close()
                        mcp_client = MCPClient(cmd_str)
                        mcp_client.start()
                        mcp_defs = default_registry.register_mcp_client(mcp_client)
                        mcp_tool_names = [d.name for d in mcp_defs]
                        active_tools = default_registry
                        print(f"[Info] Serveur MCP connecté avec succès. {len(mcp_defs)} outil(s) enregistré(s) : {', '.join(mcp_tool_names)}")
                    except Exception as exc:
                        print(f"[Erreur MCP] Impossible de connecter le serveur : {exc}")
            elif subcmd in ("disconnect", "stop", "close"):
                if mcp_client:
                    default_registry.unregister_tools(mcp_tool_names)
                    mcp_tool_names.clear()
                    mcp_client.close()
                    mcp_client = None
                    print("[Info] Serveur MCP déconnecté et ses outils ont été retirés.")
                else:
                    print("[Info] Aucun serveur MCP n'était connecté.")
            else:
                print("[Info] Sous-commandes /mcp disponibles : status, connect <cmd>, disconnect")
            continue

        if user_input in ("/kingdom", "/kingdoms") or user_input.startswith(("/kingdom ", "/kingdoms ")):
            parts = user_input.split(maxsplit=1)
            kingdom_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            if kingdom_name is None:
                print("[Info] Veuillez spécifier un nom de royaume. Usage : /kingdom [nom] (ex: /kingdom Qin)")
                continue
            print(f"[Info] Génération pour le royaume '{kingdom_name}'...")
            try:
                result = client.chat_structured(
                    model=model,
                    messages=[
                        ChatMessage(
                            role="system",
                            content="Tu es un historien spécialiste de la période des Royaumes combattants en Chine antique.",
                        ),
                        ChatMessage(
                            role="user",
                            content=f"Génère les informations historiques sur le royaume de {kingdom_name}.",
                        ),
                    ],
                    response_format=KingdomInfo,
                )
                print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
            except OllamaStructuredOutputError as exc:
                print(f"[Erreur Sortie Structurée] {exc}")
            except OllamaError as exc:
                print(f"[Erreur] {exc}")
            continue

        if user_input in ("/figure", "/figures") or user_input.startswith(("/figure ", "/figures ")):
            parts = user_input.split(maxsplit=1)
            figure_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            if figure_name is None:
                print("[Info] Veuillez spécifier un nom de personnage. Usage : /figure [nom] (ex: /figure Qin Shi Huang)")
                continue
            print(f"[Info] Génération pour le personnage '{figure_name}'...")
            try:
                result = client.chat_structured(
                    model=model,
                    messages=[
                        ChatMessage(
                            role="system",
                            content="Tu es un historien spécialiste de la période des Royaumes combattants et de l'unification par Qin.",
                        ),
                        ChatMessage(
                            role="user",
                            content=f"Génère les informations historiques sur le personnage historique {figure_name}.",
                        ),
                    ],
                    response_format=HistoricalFigure,
                )
                print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
            except OllamaStructuredOutputError as exc:
                print(f"[Erreur Sortie Structurée] {exc}")
            except OllamaError as exc:
                print(f"[Erreur] {exc}")
            continue

        if user_input in ("/structured-output", "/structured_output") or user_input.startswith(
            ("/structured-output ", "/structured_output ")
        ):
            parts = user_input.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None

            if arg is None:
                structured_mode = not structured_mode
                status = "activé" if structured_mode else "désactivé"
                print(f"[Info] Mode sortie structurée {status}. (Format: {{\"response\": ...}})")
                continue

            if arg.lower() in ("on", "true", "1", "enable", "activer"):
                structured_mode = True
                print("[Info] Mode sortie structurée activé. (Format: {\"response\": ...})")
                continue

            if arg.lower() in ("off", "false", "0", "disable", "desactiver", "désactiver"):
                structured_mode = False
                print("[Info] Mode sortie structurée désactivé.")
                continue

            query = arg
            try:
                result = client.chat_structured(
                    model=model,
                    messages=[
                        ChatMessage(role="user", content=query),
                    ],
                    response_format=StructuredResponse,
                )
                print(json.dumps(result.model_dump(), ensure_ascii=False))
                history.append(ChatMessage(role="user", content=query))
                history.append(ChatMessage(role="assistant", content=result.response))
            except OllamaStructuredOutputError as exc:
                print(f"[Erreur Sortie Structurée] {exc}")
            except OllamaError as exc:
                print(f"[Erreur] {exc}")
            continue

        user_msg = ChatMessage(role="user", content=user_input)
        history.append(user_msg)

        if structured_mode:
            sys.stdout.write("\nAssistant > ")
            sys.stdout.flush()
            try:
                result = client.chat_structured(
                    model=model,
                    messages=list(history),
                    response_format=StructuredResponse,
                )
                print(json.dumps(result.model_dump(), ensure_ascii=False))
                history.append(ChatMessage(role="assistant", content=result.response))
            except OllamaConnectionError as exc:
                print(f"\n[Erreur de connexion] {exc}")
            except OllamaModelNotFoundError as exc:
                print(f"\n[Modèle introuvable] {exc}")
                print(f"[Astuce] Exécutez 'ollama pull {model}' pour installer ce modèle.")
            except OllamaStructuredOutputError as exc:
                print(f"\n[Erreur Sortie Structurée] {exc}")
            except OllamaAPIError as exc:
                print(f"\n[Erreur API Ollama] {exc}")
            except OllamaError as exc:
                print(f"\n[Erreur] {exc}")
            continue

        sys.stdout.write("\nAssistant > ")
        sys.stdout.flush()

        response_chunks: list[str] = []
        try:
            for event in engine.run_stream(
                messages=list(history),
                model=model,
                tools=active_tools,
            ):
                if isinstance(event, TokenChunkEvent):
                    sys.stdout.write(event.token)
                    sys.stdout.flush()
                    response_chunks.append(event.token)
                elif isinstance(event, ToolCallEvent):
                    args_repr = json.dumps(event.arguments, ensure_ascii=False)
                    sys.stdout.write(f"\n[Outil appelé] {event.tool_name}({args_repr})\n")
                    sys.stdout.flush()
                elif isinstance(event, ToolResultEvent):
                    if event.is_error:
                        sys.stdout.write(f"[Erreur outil] {event.result}\n")
                    else:
                        preview = (
                            json.dumps(event.result, ensure_ascii=False)
                            if isinstance(event.result, (dict, list))
                            else str(event.result)
                        )
                        if len(preview) > 140:
                            preview = preview[:137] + "..."
                        sys.stdout.write(f"[Résultat outil] {preview}\n")
                    sys.stdout.flush()
                elif isinstance(event, ErrorEvent):
                    print(f"\n[Erreur] {event.error}")

            print()
            full_reply = "".join(response_chunks).strip()
            if full_reply:
                history.append(ChatMessage(role="assistant", content=full_reply))

        except OllamaConnectionError as exc:
            print(f"\n[Erreur de connexion] {exc}")
        except OllamaModelNotFoundError as exc:
            print(f"\n[Modèle introuvable] {exc}")
            print(f"[Astuce] Exécutez 'ollama pull {model}' pour installer ce modèle.")
        except OllamaAPIError as exc:
            print(f"\n[Erreur API Ollama] {exc}")
        except KeyboardInterrupt:
            print("\n[Génération interrompue par l'utilisateur]")
            full_reply = "".join(response_chunks).strip()
            if full_reply:
                history.append(ChatMessage(role="assistant", content=full_reply))

    if mcp_client:
        default_registry.unregister_tools(mcp_tool_names)
        mcp_client.close()


def main(argv: list[str] | None = None) -> int:
    """ Point d'entrée principal de l'application CLI initialisant l'environnement et la session.
PARAMS: - argv - LIST[STR] | NONE: arguments de ligne de commande optionnels
RETURN: code de retour entier (0 en cas de succès, 1 en cas d'erreur)"""
    args = parse_arguments(argv)
    host, model = resolve_configuration(args)

    try:
        init_database()
    except Exception as e:
        print(f"[Erreur dans l'initialisation de la BDD] {e}")
        return 1

    file_cfg = load_config_file(Path(args.config)) if args.config else {}
    mcp_cmd = args.mcp_server or os.getenv("SENSAI_MCP_SERVER") or file_cfg.get("mcp_server")
    tools_flag = (
        args.tools
        or os.getenv("SENSAI_TOOLS", "").lower() in ("1", "true", "yes")
        or bool(file_cfg.get("tools"))
        or bool(file_cfg.get("tools_enabled"))
    )

    with OllamaClient(base_url=host) as client:
        active_tools = default_registry if (tools_flag or mcp_cmd) else None
        run_session(
            client,
            model=model,
            host=host,
            tools=active_tools,
            mcp_server_cmd=mcp_cmd,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
