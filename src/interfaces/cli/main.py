import argparse
import json
import os
import re
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
from src.core.debug import debug_print, is_debug, set_debug
from src.core import sementic_cache
from src.core import sementic_cache as semantic_cache
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
from src.features.sec.security import mask_pii, validate_input_with_llm
from src.features.memory import (
    ArtifactDocument,
    ArtifactManager,
    ChatSession,
    ProfileManager,
    SessionManager,
    SessionMetadata,
    UserProfile,
)
from src.features.prompt import (
    Persona,
    PersonaManager,
    PromptVersion,
    PromptVersioningEngine,
    default_versioning_engine,
)
from src.features.tools import artifact_tool, builtin, forms, web_search
from src.features.tools.artifact_tool import (
    ARTIFACT_SYSTEM_INSTRUCTION,
    get_active_artifact,
    set_active_artifact,
)
from src.features.tools.mcp_client import MCPClient, MCPError
from src.features.tools.registry import default_registry
from src.features.simulation.human_verif import confirm_simple
from src.features.simulation.modes import MODES, AgentMode
from src.features.simulation import tools as sim_tools
from src.features.simulation.grounding import settle_reply
import requests
from src.core import auto_evaluation
from src.interfaces.cli.commands.commands import Command, Commands, command

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"

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
        help="Nom du modèle Ollama à utiliser (ex: qwen2.5:3b, llama3, mistral).",
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
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug messages and background logs.",
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
    print(" SENSAI CLI — Modular Chatbot")
    print(f" Active Model : {model}")
    print(f" Context      : {max_token}")
    print(f" Ollama Host  : {host}")
    print(f" MCP Tools    : {'Enabled' if tools_enabled else 'Disabled'}")
    if rag_enabled:
        print(" Vector RAG   : Enabled")
    print(f" Debug Mode   : {'Enabled' if is_debug() else 'Disabled'}")
    if profile_name:
        print(f" Profile      : {profile_name}")
    if persona_name:
        print(f" Persona      : {persona_name}")
    if session_id:
        print(f" Session ID   : {session_id}")
    print(" Modes        : /simulation [seed] | /encyclopedia")
    print(" Type '/help' to see commands, '/debug on|off' for debug logs, or '/exit' to quit.")
    print(" Note: Historical chronicles rely on ancient translations; cross-check info when needed.")
    print("=" * 60)

def is_french_text(text: str) -> bool:
    """Détecte rapidement si un texte semble être rédigé en français."""
    if not text:
        return False
    french_indicators = [
        " les ", " des ", " dans ", " pour ", " avec ", " était ", " étaient ",
        " mes chroniques ", " selon les ", " cette information ", " royaumes ",
        " également ", " mais ", " une ", " sont ", " été ", " période ", " guerre "
    ]
    lower = f" {text.lower()} "
    matches = sum(1 for ind in french_indicators if ind in lower)
    return matches >= 2


def build_call_messages(mode: AgentMode, history: list[ChatMessage]) -> list[ChatMessage]:
    """Construit la liste de messages envoyée au modèle pour le mode courant.
            PARAMS: - mode - AGENTMODE: mode d'agent actif
                    - history - LIST[CHATMESSAGE]: historique de la session
            RETURN: liste de messages (le prompt système du mode remplace les autres messages système)"""

    if mode.system_prompt:
        recent = [m for m in history if m.role != "system"]
    if mode.force_tools:
        recent = recent[-1:]
        messages = [ChatMessage(role="system", content=mode.system_prompt)] + recent
    else:
        messages = list(history)

    # Si un message système est actif, garantir la directive absolue de réponse en anglais
    if messages and messages[0].role == "system":
        content = messages[0].content
        content = re.sub(r"Langue d'échange\s*:\s*français", "Langue d'échange : english", content, flags=re.IGNORECASE)
        if "always respond in english" not in content.lower():
            content = f"{content}\n\n[CRITICAL DIRECTIVE]\nYou must formulate your ENTIRE response in English. Never reply in French."
        messages[0] = ChatMessage(role="system", content=content)

    return messages


def run_session(
    client: OllamaClient,
    model: str,
    host: str,
    tools: Any = None,
    mcp_server_cmd: str | None = None,
    session_id: str | None = None,
    profile_name: str | None = None,
    persona_name: str | None = None,
    session_manager: SessionManager | None = None,
    profile_manager: ProfileManager | None = None,
    artifact_manager: ArtifactManager | None = None,
    persona_manager: PersonaManager | None = None,
    versioning_engine: PromptVersioningEngine | None = None,
    max_tokens: int = 2000,
    rag_enabled: bool = True,
    cache_build: bool = False,
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
                    - cache_build - BOOL: indicateur d'activation du cache sémantique
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
            print(f"[Persona Warning] {exc}")

    current_session: ChatSession
    if session_id:
        try:
            current_session = session_manager.load_session(session_id)
            if getattr(current_session, "metadata", None) and current_session.metadata.model:
                model = current_session.metadata.model
            c_toks = getattr(getattr(current_session, "metadata", None), "context_tokens", 0)
            singleton_token.context_tokens = c_toks if isinstance(c_toks, (int, float)) else 0
            t_toks = getattr(getattr(current_session, "metadata", None), "total_tokens", 0)
            singleton_token.budget_tokens = t_toks if isinstance(t_toks, (int, float)) else 0
            print(f"[Info] Session '{session_id}' loaded ({len(current_session.messages)} messages).")
        except FileNotFoundError:
            print(f"[Warning] Session '{session_id}' not found. Initializing a new session.")
            current_session = session_manager.create_session(profile=current_profile, model=model)
            singleton_token.context_tokens = 0
            singleton_token.budget_tokens = 0
    else:
        current_session = session_manager.create_session(profile=current_profile, model=model)
        singleton_token.context_tokens = 0
        singleton_token.budget_tokens = 0

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
            print(f"[Info] MCP server started ({mcp_server_cmd}). {len(mcp_defs)} tool(s) loaded.")
        except Exception as exc:
            print(f"[MCP Warning] Failed to connect to MCP server: {exc}")

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
    engines = {
        name: ConversationEngine(client=client, registry=m.registry, max_tool_iterations=m.max_tool_iterations)
        for name, m in MODES.items()
    }
    current_mode: AgentMode = MODES["encyclopedia"]
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
        margin = (max_tokens * 15) / 100 # Retirer 15% du context legth afin de laisser du context au model pour la compression de l'historique
        token_with_margin = max_tokens - margin
        ctx_toks = singleton_token.context_tokens if isinstance(singleton_token.context_tokens, (int, float)) else 0
        if ctx_toks > 0 and ctx_toks >= token_with_margin:
            history = mem.enforce_token_budget(model, client, history, max_history_tokens=max_tokens)
            current_session.messages = list(history)
            command_handler.history = history

        prompt = "\nYou > " if current_mode.name == "encyclopedia" else f"\nYou [{current_mode.name}] > "
        try:
            user_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession interrupted.")
            break

        if not user_input:
            print("[Info] Please enter a non-empty message.")
            continue

        if user_input == "/clear-cache":
            sementic_cache.clean_cache()
            print("[Info] Cache cleared successfully!")
            continue

        mode_cmd, *mode_args = user_input.split()
        if mode_cmd in ("/simulation", "/encyclopedia"):
            target = MODES[mode_cmd.lstrip("/")]
            if target is current_mode and target.name == "encyclopedia":
                print("[Info] Already in encyclopedia mode.")
                continue
            if target is current_mode and not confirm_simple("A simulation is already in progress. Replace with a new game?"):
                continue
            if current_mode.on_exit and target is not current_mode:
                current_mode.on_exit()
            current_mode = target
            if current_mode.on_enter:
                print(current_mode.on_enter(mode_args))
                if any(tag in model for tag in (":0.5b", ":1.5b")):
                    print(f"[Tip] {model} might have issues calling tools: try '/model qwen2.5:7b' if needed.")
            else:
                print("[Info] Encyclopedia mode activated. Current simulation closed.")
            continue

        safe_input, _has_confidential_data = mask_pii(user_input)

        cmd_name = command_handler.check_command(safe_input)
        if cmd_name:
            if cmd_name in ("/kingdom", "/figure"):
                parts = safe_input.split(maxsplit=1)
                target_entity = parts[1].strip() if len(parts) > 1 else ""
                if target_entity:
                    is_valid, error_message = validate_input_with_llm(target_entity, client, model)
                    if not is_valid:
                        print(f"\nAssistant > {error_message}")
                        continue
            should_continue = command_handler.execute_command(cmd_name, safe_input)
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

        from src.features.pdf import build_pdf_historical_veracity_prompt, detect_and_prepare_pdf_audit

        pdf_audit = detect_and_prepare_pdf_audit(safe_input)
        if pdf_audit is not None:
            _pdf_path, pdf_instruction, pdf_info = pdf_audit
            print(
                f"[PDF Detected] '{pdf_info.file_name}' ({pdf_info.extracted_pages}/{pdf_info.total_pages} page(s), "
                f"{len(pdf_info.content)} chars) — Historical veracity audit..."
            )
            safe_input = build_pdf_historical_veracity_prompt(pdf_info, pdf_instruction)

        is_valid, error_message = validate_input_with_llm(safe_input, client, model)
        if not is_valid:
            print(f"\nAssistant > {error_message}")
            continue

        augmented_input = safe_input
        rag_found = False

        if cache_build and current_mode.free_chat and pdf_audit is None:
            try:
                cache_result = sementic_cache.get_info_cache(prompt=safe_input, ollama_url=host, model=model)
                if cache_result is not None and is_french_text(cache_result):
                    debug_print("[Cache] Discarding cached entry because it is in French.")
                    cache_result = None

                if cache_result is not None:
                    debug_print("[SEMANTIC CACHE] Cached question found.")
                    sys.stdout.write("\nAssistant > ")
                    print(cache_result)
                    history.append(ChatMessage(role="user", content=safe_input))
                    history.append(ChatMessage(role="assistant", content=cache_result))
                    continue
            except Exception:
                pass

        rag_ctx = None

        if rag_enabled and current_mode.free_chat:
            try:
                from src.RAG.retriever import retrieve_rag_context
                rag_query = (
                    f"{pdf_audit[1]} {pdf_audit[2].file_name} {pdf_audit[2].content[:250]}".strip()
                    if pdf_audit is not None
                    else safe_input
                )
                rag_res = retrieve_rag_context(
                    rag_query,
                    ollama_url=host,
                    ollama_model=model,
                    fallback_web=True,
                    return_count=True,
                )
                if isinstance(rag_res, tuple):
                    rag_ctx, source_count = rag_res
                else:
                    rag_ctx = rag_res
                    source_count = rag_ctx.count("[Source :") if rag_ctx else 0

                if rag_ctx:
                    rag_found = True
                    if source_count >= 2:
                        debug_print(f"[RAG] Historical context sufficient ({source_count} sources found in chronicles).")
                        augmented_input = (
                            f"You are an expert strategic advisor on the 7 Warring States of Ancient China.\n\n"
                            f"HISTORICAL DOCUMENTS (archives locales fournies ci-dessous ({source_count} sources trouvées)):\n"
                            f"======================\n"
                            f"{rag_ctx}\n"
                            f"======================\n\n"
                            f"RESPONSE INSTRUCTIONS:\n"
                            f"1. CONTEXT USAGE: Synthesize and respond directly by relying on the historical facts attested in the documents above to enlighten the Lord. Call the 'web_search' tool only if you judge it necessary.\n"
                            f"2. HANDLING MISSING INFORMATION: If and only if the documents above contain absolutely NO information to answer the question, respond only with 'My chronicles do not mention this information.' NEVER use this phrase if you provide any relevant facts or partial answers in your response.\n"
                            f"3. ARMY SIZE CORRECTION: The ancient texts (Shiji and Zhan Guo Ce) contain classical translation conventions. If they mention Chinese army sizes in tens of thousands (e.g., 20,000 or 60,000), it stems from the Chinese numeral unit 'Wan' (10,000). Always multiply these military counts by 10 (e.g., 200,000) to reflect historical reality.\n"
                            f"4. ANTI-CONFUSION: The documents may relate stories of multiple different generals (e.g., Li Xin, Han Xin, Wang Jian). Do NOT mix their accounts. Only answer with facts explicitly associated with the topic requested by the Lord.\n"
                            f"5. LANGUAGE: You must ALWAYS formulate your entire response in English.\n\n"
                            f"Lord's Question: {safe_input}"
                        )
                    elif source_count == 1:
                        debug_print("[RAG] Sources locales parcellaires (1 seule source). Complément automatique via recherche Web...")
                        augmented_input = (
                            f"You are an expert strategic advisor on the 7 Warring States of Ancient China.\n\n"
                            f"### ARCHIVES ET SOURCES COMPLÉMENTAIRES :\n"
                            f"======================\n"
                            f"{rag_ctx}\n"
                            f"======================\n\n"
                            f"RESPONSE INSTRUCTIONS:\n"
                            f"1. CONTEXT USAGE: Les archives locales ne contiennent qu'une seule source très partielle. Ne te limite pas à une réponse courte de 3 lignes ! Utilize both local chronicle excerpts and Web search findings to develop a rich, structured answer.\n"
                            f"2. HANDLING MISSING INFORMATION: If and only if the documents above contain absolutely NO information to answer the question, respond only with 'My chronicles do not mention this information.' NEVER use this phrase if you provide any relevant facts or partial answers in your response.\n"
                            f"3. ARMY SIZE CORRECTION: The ancient texts (Shiji and Zhan Guo Ce) contain classical translation conventions. If they mention Chinese army sizes in tens of thousands (e.g., 20,000 or 60,000), it stems from the Chinese numeral unit 'Wan' (10,000). Always multiply these military counts by 10 (e.g., 200,000) to reflect historical reality.\n"
                            f"4. ANTI-CONFUSION: The documents may relate stories of multiple different generals (e.g., Li Xin, Han Xin, Wang Jian). Do NOT mix their accounts. Only answer with facts explicitly associated with the topic requested by the Lord.\n"
                            f"5. LANGUAGE: You must ALWAYS formulate your entire response in English.\n\n"
                            f"Lord's Question: {safe_input}"
                        )
                    else:
                        debug_print("[RAG] Aucune archive locale trouvée. Bascule automatique sur la recherche Web...")
                        augmented_input = (
                            f"You are an expert strategic advisor on the 7 Warring States of Ancient China.\n\n"
                            f"### INFORMATIONS WEB :\n"
                            f"======================\n"
                            f"{rag_ctx}\n"
                            f"======================\n\n"
                            f"RESPONSE INSTRUCTIONS:\n"
                            f"1. CONTEXT USAGE: Aucune archive locale n'a été trouvée pour cette question. Rely on the Web search findings above to formulate a complete and documented answer.\n"
                            f"2. ARMY SIZE CORRECTION: If army sizes are mentioned in tens of thousands, remember the classical Chinese numeral unit 'Wan' (10,000) and multiply by 10 (e.g., 200,000) to reflect historical reality.\n"
                            f"3. ANTI-CONFUSION: Do not mix stories of different historical figures. Only answer with facts explicitly associated with the requested topic.\n"
                            f"4. LANGUAGE: You must ALWAYS formulate your entire response in English.\n\n"
                            f"Lord's Question: {safe_input}"
                        )
            except Exception:
                pass

        if not rag_found and active_tools is not None:
            augmented_input = (
                f"{safe_input}\n\n"
                f"[Système : Aucune archive locale n'a été trouvée dans les chroniques historiques pour cette question. "
                f"Utilise l'outil 'web_search' pour rechercher les informations manquantes si nécessaire.]"
            )
        user_msg = ChatMessage(role="user", content=safe_input)
        history.append(user_msg)

        if structured_mode and current_mode.free_chat:
            sys.stdout.write("\nAssistant > ")
            sys.stdout.flush()
            try:
                structured_messages = list(history)
                if augmented_input != safe_input and structured_messages and structured_messages[-1].role == "user":
                    structured_messages[-1] = ChatMessage(role="user", content=augmented_input)
                result = client.chat_structured(
                    model=model,
                    messages=structured_messages,
                    response_format=StructuredResponse,
                    track_as_context=True,
                )
                eval_res = auto_evaluation.evaluate_ai_response(
                    client=client,
                    model=model,
                    question_user=safe_input,
                    rag_context=rag_ctx,
                    reponse_assistant=result.response,
                )
                if auto_evaluation.interpret_result(eval_res):
                    debug_print("[Auto-Evaluation] Score < 3 or hallucination detected! Reworking structured response...")
                    result = auto_evaluation.rework_structured_response(
                        client=client,
                        model=model,
                        question_user=safe_input,
                        rag_context=rag_ctx,
                        reponse_assistant=result.response,
                        evaluation=eval_res,
                        response_format=StructuredResponse,
                    )
                    auto_evaluation.evaluate_ai_response(
                        client=client,
                        model=model,
                        question_user=safe_input,
                        rag_context=rag_ctx,
                        reponse_assistant=result.response,
                    )
                print(json.dumps(result.model_dump(), ensure_ascii=False))
                history.append(ChatMessage(role="assistant", content=result.response))
                current_session.messages = list(history)
                current_session.metadata.model = model
                current_session.metadata.context_tokens = singleton_token.context_tokens
                current_session.metadata.total_tokens = singleton_token.budget_tokens
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())
            except OllamaConnectionError as exc:
                print(f"\n[Connection Error] {exc}")
            except OllamaModelNotFoundError as exc:
                print(f"\n[Model Not Found] {exc}")
                print(f"[Tip] Run 'ollama pull {model}' to install this model.")
            except OllamaStructuredOutputError as exc:
                print(f"\n[Structured Output Error] [Erreur Sortie Structurée] {exc}")
            except OllamaAPIError as exc:
                print(f"\n[Ollama API Error] {exc}")
            except OllamaError as exc:
                print(f"\n[Error] {exc}")
            continue

        simulation_turn = current_mode.force_tools
        if not simulation_turn:
            sys.stdout.write("\nAssistant > ")
            sys.stdout.flush()

        engine = engines[current_mode.name]
        mode_tools = current_mode.registry if current_mode.force_tools else active_tools
        call_messages = build_call_messages(current_mode, history)
        sim_tools.configure(client, lambda: model, host)
        if augmented_input != safe_input and call_messages and call_messages[-1].role == "user":
            call_messages[-1] = ChatMessage(role="user", content=augmented_input)

        response_chunks: list[str] = []
        tool_results: list[dict] = []
        try:
            for event in engine.run_stream(
                messages=call_messages,
                model=model,
                tools=mode_tools,
            ):
                if isinstance(event, TokenChunkEvent):
                    response_chunks.append(event.token)
                    if not simulation_turn:
                        sys.stdout.write(event.token)
                        sys.stdout.flush()
                elif isinstance(event, ToolCallEvent):
                    args_repr = json.dumps(event.arguments, ensure_ascii=False)
                    sys.stdout.write(f"\n[Outil appelé] {event.tool_name}({args_repr})\n")
                    sys.stdout.flush()
                elif isinstance(event, ToolResultEvent):
                    if event.is_error:
                        sys.stdout.write(f"[Erreur outil] {event.result}\n")
                    else:
                        if isinstance(event.result, dict):
                            tool_results.append(event.result)
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
                    print(f"\n[Error] {event.error}")

            print()
            full_reply = "".join(response_chunks).strip()

            if simulation_turn:
                full_reply, problems = settle_reply(full_reply, tool_results, sim_tools.kingdom_names())
                for problem in problems:
                    print(f"[Check] {problem}")
                if full_reply:
                    print(f"\nAssistant > {full_reply}")
            elif full_reply and current_mode.free_chat:
                eval_res = auto_evaluation.evaluate_ai_response(
                    client=client,
                    model=model,
                    question_user=safe_input,
                    rag_context=rag_ctx,
                    reponse_assistant=full_reply,
                )
                if auto_evaluation.interpret_result(eval_res):
                    debug_print("[Auto-Evaluation] Score < 3 or hallucination detected!")
                    debug_print("[Auto-Evaluation] Reworking response based on judge feedback...")
                    sys.stdout.write("\nAssistant (revised) > ")
                    sys.stdout.flush()
                    reworked_chunks: list[str] = []
                    try:
                        for chunk in auto_evaluation.rework_response_stream(
                            client=client,
                            model=model,
                            question_user=safe_input,
                            rag_context=rag_ctx,
                            reponse_assistant=full_reply,
                            evaluation=eval_res,
                        ):
                            sys.stdout.write(chunk)
                            sys.stdout.flush()
                            reworked_chunks.append(chunk)
                        print()
                        if reworked_chunks:
                            full_reply = "".join(reworked_chunks).strip()
                            auto_evaluation.evaluate_ai_response(
                                client=client,
                                model=model,
                                question_user=safe_input,
                                rag_context=rag_ctx,
                                reponse_assistant=full_reply,
                            )
                    except Exception as err:
                        debug_print(f"\n[Auto-Evaluation] Error during response rework: {err}")

            if simulation_turn and not full_reply:
                history.pop()
            elif full_reply:
                history.append(ChatMessage(role="assistant", content=full_reply))
                current_session.messages = list(history)
                current_session.metadata.model = model
                current_session.metadata.context_tokens = singleton_token.context_tokens
                current_session.metadata.total_tokens = singleton_token.budget_tokens
                if cache_build and current_mode.free_chat:
                    try:
                        sementic_cache.add_to_cache(prompt=safe_input, llm_response=full_reply, ollama_url=host)
                    except Exception as e:
                        debug_print(f"[Cache Error] {e}")
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())

        except OllamaConnectionError as exc:
            print(f"\n[Connection Error] {exc}")
        except OllamaModelNotFoundError as exc:
            print(f"\n[Model Not Found] {exc}")
            print(f"[Tip] Run 'ollama pull {model}' to install this model.")
        except OllamaAPIError as exc:
            print(f"\n[Ollama API Error] {exc}")
        except KeyboardInterrupt:
            print("\n[Generation interrupted by user]")
            full_reply = "".join(response_chunks).strip()
            if full_reply and not simulation_turn:
                history.append(ChatMessage(role="assistant", content=full_reply))
                current_session.messages = list(history)
                current_session.metadata.model = model
                current_session.metadata.context_tokens = singleton_token.context_tokens
                current_session.metadata.total_tokens = singleton_token.budget_tokens
                session_manager.save_session(current_session)
                artifact_manager.save_artifact(current_session.metadata.session_id, get_active_artifact())
            else:
                history.pop()

    if current_mode.on_exit:
        current_mode.on_exit()

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
    file_cfg = load_config_file(Path(args.config)) if args.config else {}

    # Initialize debug mode from CLI flag, env var, or config file
    debug_flag = (
        bool(args.debug)
        or os.getenv("SENSAI_DEBUG", "").lower() in ("1", "true", "yes")
        or bool(file_cfg.get("debug", False))
    )
    set_debug(debug_flag)

    context_length = 2000
    try:
        response = requests.post(host + "/api/show", json={"model": model})
        if response.status_code == 200:
            show_data = response.json()
            model_details = show_data.get("model_info", {})
            for key, value in model_details.items():
                if "context_length" in key:
                    context_length = value
                    break
            debug_print(f"[Info] Context length detected for {model}: {context_length}")
        else:
            debug_print(f"[Warning] Model {model} not found or error. Code: {response.status_code}")
    except Exception as e:
        debug_print(f"[Warning] Error retrieving context length: {e}")
        context_length = 2000
    try:
        init_database()
    except Exception as e:
        print(f"[Error initializing database] {e}")
        return 1

    cache_build = False
    try:
        sementic_cache.create_cache()
        cache_build = True
    except Exception as e:
        print(f"[Error creating cache] {e}")
        cache_build = False

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
    timeout = float(os.getenv("SENSAI_TIMEOUT") or file_cfg.get("request_timeout") or 300.0)

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
            cache_build=cache_build
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
