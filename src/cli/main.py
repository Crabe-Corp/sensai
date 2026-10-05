import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from src.core.db.database import init_database, get_kingdom_stats, update_kingdom_gold, get_active_diplomacy

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.ollama_client import (
    ChatMessage,
    OllamaAPIError,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)

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
    return parser.parse_args(argv)


def print_banner(model: str, host: str) -> None:
    print("=" * 60)
    print(" SENSAI CLI — Chatbot Local (Socle [B1])")
    print(f" Modèle actif : {model}")
    print(f" Hôte Ollama  : {host}")
    print(" Tapez '/help' pour voir les commandes ou '/exit' pour quitter.")
    print("=" * 60)


def print_help() -> None:
    print("\nCommandes disponibles :")
    print("  /help          : Affiche ce message d'aide")
    print("  /clear         : Réinitialise l'historique de la session")
    print("  /history       : Affiche le nombre de messages échangés")
    print("  /models        : Liste les modèles installés sur le serveur Ollama")
    print("  /model [nom]   : Affiche ou change le modèle actif sans redémarrer")
    print("  /exit | /quit  : Quitte l'application\n")


def run_session(client: OllamaClient, model: str, host: str) -> None:
    history: list[ChatMessage] = []
    print_banner(model, host)
    init_database()

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

        user_msg = ChatMessage(role="user", content=user_input)
        history.append(user_msg)

        sys.stdout.write("\nAssistant > ")
        sys.stdout.flush()

        response_chunks: list[str] = []
        try:
            for chunk in client.chat_stream(model=model, messages=list(history)):
                sys.stdout.write(chunk)
                sys.stdout.flush()
                response_chunks.append(chunk)
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
        print(f"[Erreur dans l'initisalisation de la BDD] {e}")
        return 1

    with OllamaClient(base_url=host) as client:
        run_session(client, model=model, host=host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
