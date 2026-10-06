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
from src.features.tools.registry import default_registry

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"


def load_config_file(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_configuration(cli_args: argparse.Namespace) -> tuple[str, str]:
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
    return parser.parse_args(argv)


def print_banner(model: str, host: str, tools_enabled: bool = False) -> None:
    print("=" * 60)
    print(" SENSAI CLI — Chatbot Modulaire")
    print(f" Modèle actif : {model}")
    print(f" Hôte Ollama  : {host}")
    print(f" Outils MCP   : {'Activés' if tools_enabled else 'Désactivés'}")
    print(" Tapez '/help' pour voir les commandes ou '/exit' pour quitter.")
    print("=" * 60)


def print_help() -> None:
    print("\nCommandes disponibles :")
    print("  /help                     : Affiche ce message d'aide")
    print("  /clear                    : Réinitialise l'historique de la session")
    print("  /history                  : Affiche le nombre de messages échangés")
    print("  /models                   : Liste les modèles installés sur le serveur Ollama")
    print("  /model [nom]              : Affiche ou change le modèle actif sans redémarrer")
    print("  /tools [on|off]           : Liste les outils disponibles ou active/désactive les outils")
    print("  /kingdom [nom]            : Génère une fiche de royaume au format JSON strict")
    print("  /figure [nom]             : Génère une fiche de personnage historique")
    print("  /structured-output [msg]  : Active/désactive le mode JSON ou soumet une requête")
    print("  /exit | /quit             : Quitte l'application\n")


def run_session(
    client: OllamaClient,
    model: str,
    host: str,
    tools: Any = None,
) -> None:
    history: list[ChatMessage] = []
    structured_mode: bool = False
    active_tools = tools
    tools_enabled = active_tools is not None

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


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    host, model = resolve_configuration(args)

    try:
        init_database()
    except Exception as e:
        print(f"[Erreur dans l'initialisation de la BDD] {e}")
        return 1

    with OllamaClient(base_url=host) as client:
        active_tools = default_registry if args.tools else None
        run_session(client, model=model, host=host, tools=active_tools)
    return 0


if __name__ == "__main__":
    sys.exit(main())
