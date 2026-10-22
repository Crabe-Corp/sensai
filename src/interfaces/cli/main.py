import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.core.db.database import init_database
from src.core import memory_management as mem, singleton_token
from src.core.sec.security import mask_pii, validate_input_with_llm
from src.core.engine import (ConversationEngine, EngineEvent, ErrorEvent, TokenChunkEvent, ToolCallEvent, ToolResultEvent,)
from src.core.ollama_client import (ChatMessage, OllamaAPIError, OllamaClient, OllamaConnectionError, OllamaError, OllamaModelNotFoundError, OllamaStructuredOutputError,)
from src.core.schemas import HistoricalFigure, KingdomInfo, StructuredResponse
from src.features.memory import (ArtifactDocument, ArtifactManager, ChatSession, ProfileManager, SessionManager, SessionMetadata, UserProfile,)
from src.features.prompt import (Persona, PersonaManager, PromptVersion, PromptVersioningEngine, default_versioning_engine,)
from src.features.tools import artifact_tool, builtin, web_search
from src.features.tools.artifact_tool import (ARTIFACT_SYSTEM_INSTRUCTION, get_active_artifact, set_active_artifact,)
from src.features.tools.mcp_client import MCPClient, MCPError
from src.features.tools.registry import default_registry
import requests
from src.interfaces.cli.commands.commands import Command, Commands, command

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
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Identifiant de la session à charger ou reprendre.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Nom du profil utilisateur à charger (ex: default, historien).",
    )
    parser.add_argument(
        "--persona",
        type=str,
        default=None,
        help="Nom ou fichier de la persona à charger (ex: scribe_qin, erudit_zhao).",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        default=True,
        help="Activer l'enrichissement documentaire automatique RAG.",
    )
    
    return parser.parse_args(argv)


def print_banner(
    model: str,
    max_token : int,
    host: str,
    tools_enabled: bool = False,
    profile_name: str | None = None,
    persona_name: str | None = None,
    session_id: str | None = None,
    rag_enabled: bool = False,
) -> None:
    """Affiche la bannière d'accueil de la CLI avec les paramètres de connexion actifs.
            PARAMS: - model - STR: nom du modèle Ollama en cours d'utilisation
                    - host - STR: URL du serveur Ollama
                    - tools_enabled - BOOL: indicateur d'activation du support des outils
                    - profile_name - STR | NONE: nom du profil utilisateur actif
                    - persona_name - STR | NONE: nom de la persona active
                    - session_id - STR | NONE: identifiant de la session courante
            RETURN: None"""

    print("=" * 60)
    print(" SENSAI CLI — Chatbot Modulaire")
    print(f" Modèle actif : {model}")
    print(f" Context      : {max_token}")
    print(f" Hôte Ollama  : {host}")
    print(f" Outils MCP   : {'Activés' if tools_enabled else 'Désactivés'}")
    if rag_enabled:
        print(" RAG vectoriel: Activé")
    if profile_name:
        print(f" Profil       : {profile_name}")
    if persona_name:
        print(f" Persona      : {persona_name}")
    if session_id:
        print(f" Session ID   : {session_id}")
    print(" Tapez '/help' pour voir les commandes ou '/exit' pour quitter.")
    print("=" * 60)

def run_session(client: OllamaClient, model: str, host: str, tools: Any = None, mcp_server_cmd: str | None = None,
                session_id: str | None = None, profile_name: str | None = None, persona_name: str | None = None,
                session_manager: SessionManager | None = None, profile_manager: ProfileManager | None = None,
                artifact_manager: ArtifactManager | None = None, persona_manager: PersonaManager | None = None,
                versioning_engine: PromptVersioningEngine | None = None, max_tokens: int = 2000, rag_enabled: bool = True,
) -> None:
    """Gère la boucle interactive du chatbot CLI, l'historique et les commandes slash.
            PARAMS: - client - OLLAMACLIENT: instance active du client HTTP Ollama
                    - model - STR: nom du modèle Ollama à utiliser
                    - host - STR: URL du serveur Ollama
                    - tools - ANY: registre ou outils optionnels à exposer au LLM
                    - mcp_server_cmd - STR | NONE: commande de démarrage d'un serveur MCP externe
                    - session_id - STR | NONE: identifiant d'une session à restaurer
                    - profile_name - STR | NONE: nom du profil utilisateur à charger
                    - persona_name - STR | NONE: nom ou fichier de la persona à charger
                    - session_manager - SESSIONMANAGER | NONE: gestionnaire de sessions persistant
                    - profile_manager - PROFILEMANAGER | NONE: gestionnaire de profils utilisateur
                    - artifact_manager - ARTIFACTMANAGER | NONE: gestionnaire de livrables d'état
                    - persona_manager - PERSONAMANAGER | NONE: gestionnaire de personas
                    - versioning_engine - PROMPTVERSIONINGENGINE | NONE: moteur de versioning de prompts
            RETURN: None"""

    session_manager = session_manager or SessionManager()
    profile_manager = profile_manager or ProfileManager()
    artifact_manager = artifact_manager or ArtifactManager()
    versioning_engine = versioning_engine or default_versioning_engine
    persona_manager = persona_manager or PersonaManager(versioning_engine=versioning_engine)

    current_profile: UserProfile | None = None
    if profile_name:
        current_profile = profile_manager.get_or_create_profile(profile_name)

    current_persona: Persona | None = None
    if persona_name:
        try:
            current_persona = persona_manager.load_persona(persona_name)
        except Exception as exc:
            print(f"[Avertissement Persona] {exc}")

    current_session: ChatSession
    if session_id:
        try:
            current_session = session_manager.load_session(session_id)
            if current_session.metadata.model:
                model = current_session.metadata.model
            print(f"[Info] Session '{session_id}' chargée ({len(current_session.messages)} messages).")
        except FileNotFoundError:
            print(f"[Avertissement] Session '{session_id}' introuvable. Initialisation d'une nouvelle session.")
            current_session = session_manager.create_session(profile=current_profile, model=model)
    else:
        current_session = session_manager.create_session(profile=current_profile, model=model)

    current_artifact = artifact_manager.get_or_create_artifact(current_session.metadata.session_id)
    set_active_artifact(current_artifact, session_id=current_session.metadata.session_id, manager=artifact_manager)

    history: list[ChatMessage] = list(current_session.messages)
    structured_mode: bool = False
    active_tools = tools
    tools_enabled = active_tools is not None

    if current_persona:
        p_content = current_persona.system_prompt
        if tools_enabled and "update_artifact" not in p_content:
            p_content = f"{p_content}\n\n{ARTIFACT_SYSTEM_INSTRUCTION}"
        if history and history[0].role == "system":
            history[0].content = p_content
        else:
            history.insert(0, ChatMessage(role="system", content=p_content))
    elif tools_enabled:
        if not history:
            history.append(ChatMessage(role="system", content=ARTIFACT_SYSTEM_INSTRUCTION))
        elif history[0].role == "system":
            if "update_artifact" not in history[0].content:
                history[0].content = f"{history[0].content}\n\n{ARTIFACT_SYSTEM_INSTRUCTION}"
        else:
            history.insert(0, ChatMessage(role="system", content=ARTIFACT_SYSTEM_INSTRUCTION))
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

    print_banner(
        model,
        max_tokens,
        host,
        tools_enabled=tools_enabled,
        profile_name=current_profile.username if current_profile else None,
        persona_name=current_persona.name if current_persona else None,
        session_id=current_session.metadata.session_id,
        rag_enabled=rag_enabled,
    )
    init_database()
    engine = ConversationEngine(client=client, registry=default_registry)
    command_handler = Commands(
        client=client,
        model=model,
        host=host,
        history=history,
        current_session=current_session,
        current_profile=current_profile,
        session_manager=session_manager,
        profile_manager=profile_manager,
        artifact_manager=artifact_manager,
        current_persona=current_persona,
        persona_manager=persona_manager,
        versioning_engine=versioning_engine,
        max_tokens=max_tokens,
        rag_enabled=rag_enabled,
        structured_mode=structured_mode,
        active_tools=active_tools,
        tools_enabled=tools_enabled,
        mcp_client=mcp_client,
        mcp_tool_names=mcp_tool_names,
    )

    while True:
        if singleton_token.budget_tokens >= max_tokens:
            history = mem.enforce_token_budget(model, client, history, max_history_tokens=max_tokens)
            current_session.messages = list(history)
            command_handler.history = history

        try:
            user_input = input("\nYou > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession interrompue.")
            break

        if not user_input:
            print("[Info] Veuillez saisir un message non vide.")
            continue
        cmd_name = command_handler.check_command(user_input)
        if cmd_name:
            should_continue = command_handler.execute_command(cmd_name, user_input)
            model = command_handler.model
            rag_enabled = command_handler.rag_enabled
            structured_mode = command_handler.structured_mode
            active_tools = command_handler.active_tools
            current_session = command_handler.current_session
            current_profile = command_handler.current_profile
            mcp_client = command_handler.mcp_client
            mcp_tool_names = command_handler.mcp_tool_names
            history = command_handler.history
            if not should_continue:
                break
            continue


        safe_input, _has_confidential_data = mask_pii(user_input)

        is_valid, error_message = validate_input_with_llm(safe_input, client, model)
        if not is_valid:
            print(f"\nAssistant > {error_message}")
            continue

        augmented_input = safe_input
        if rag_enabled:
            try:
                from src.RAG.retriever import retrieve_rag_context
                rag_ctx = retrieve_rag_context(safe_input, ollama_url=host, ollama_model=model)
                if rag_ctx:
                    print("[RAG] Contexte historique injecté depuis les chroniques.")
                    augmented_input = (
                        f"Tu es un conseiller stratégique des 7 Royaumes Combattants. "
                        f"Réponds en t'appuyant sur ce contexte historique :\n\n"
                        f"{rag_ctx}\n\n"
                        f"Question : {safe_input}"
                    )
            except Exception:
                pass

        user_msg = ChatMessage(role="user", content=augmented_input)
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
                current_session.messages = list(history)
                current_session.metadata.model = model
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())
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
                current_session.messages = list(history)
                current_session.metadata.model = model
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())

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
                current_session.messages = list(history)
                current_session.metadata.model = model
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())

    current_session = command_handler.current_session
    mcp_client = command_handler.mcp_client
    mcp_tool_names = command_handler.mcp_tool_names
    has_real_messages = any(m.role in ("user", "assistant") for m in current_session.messages)
    if not has_real_messages:
        session_manager.delete_session(current_session.metadata.session_id)
        doc = get_active_artifact()
        if not doc.sections:
            for ext in ("md", "json"):
                p = artifact_manager.get_storage_path(current_session.metadata.session_id, ext)
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
    else:
        artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())

    if mcp_client:
        default_registry.unregister_tools(mcp_tool_names)
        mcp_client.close()


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal de l'application CLI initialisant l'environnement et la session.
            PARAMS: - argv - LIST[STR] | NONE: arguments de ligne de commande optionnels
            RETURN: code de retour entier (0 en cas de succès, 1 en cas d'erreur)"""

    args = parse_arguments(argv)
    host, model = resolve_configuration(args)

    try:
        response = requests.post(host + "/api/show", json={"model": model})
        if response.status_code == 200:
            show_data = response.json()
            model_details = show_data.get("model_info", {})
            for key, value in model_details.items():
                if "context_length" in key:
                    context_length = value
                    break
            print(f"[Info] Context length détecté pour {model} : {context_length}")
        else:
            print(f"[Avertissement] Modèle {model} introuvable ou erreur. Code: {response.status_code}")
    except Exception as e:
        print(f"[Erreur dans la récupération du context length] {e}")
        context_length = 2000
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
    
    profile_name = args.profile or "default"
    persona_name = args.persona or os.getenv("SENSAI_PERSONA") or file_cfg.get("persona")
    session_id = args.session
    timeout = float(os.getenv("SENSAI_TIMEOUT") or file_cfg.get("request_timeout") or 180.0)

    with OllamaClient(base_url=host, timeout=timeout) as client:
        active_tools = default_registry if (tools_flag or mcp_cmd) else None
        run_session(
            client,
            model=model,
            host=host,
            tools=active_tools,
            mcp_server_cmd=mcp_cmd,
            session_id=session_id,
            profile_name=profile_name,
            persona_name=persona_name,
            max_tokens = context_length,
            rag_enabled=args.rag,
        )
    return 0

if __name__ == "__main__":
    sys.exit(main())

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_HOST",
    "DEFAULT_MODEL",
    "Commands",
    "Command",
    "command",
    "load_config_file",
    "main",
    "parse_arguments",
    "print_banner",
    "resolve_configuration",
    "run_session",
]
