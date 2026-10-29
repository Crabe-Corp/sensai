from __future__ import annotations
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from src.core import singleton_token
from src.core.debug import is_debug, set_debug
from src.core.ollama_client import (ChatMessage, OllamaClient, OllamaError, OllamaStructuredOutputError,)
from src.core.schemas import HistoricalFigure, KingdomInfo
from src.features.memory import (ArtifactManager, ChatSession, ProfileManager, SessionManager, UserProfile,)
from src.features.prompt import (Persona, PersonaManager, PromptVersion, PromptVersioningEngine, default_versioning_engine,)
from src.features.sec.security import mask_pii
from src.features.tools.artifact_tool import (ARTIFACT_SYSTEM_INSTRUCTION, get_active_artifact, set_active_artifact,)
from src.features.tools.mcp_client import MCPClient
from src.features.tools.registry import default_registry

COMMANDS_LIST: list[str] = ["/help", "/clear", "/history", "/budget", "/exit", "/quit", "/rag", "/debug", "/clear-cache", "/clearcache", "/mcp", "/session", "/sessions", "/profile", "/persona","/personas","/prompt","/prompts","/models","/model","/tools","/structured-output","/structured_output","/artifact","/artifacts", "/export", "/exports", "/kingdom", "/kingdoms", "/figure", "/figures",]


class Commands:
    """Gestionnaire centralisé des commandes interactives de la CLI SENSAI."""
    def __init__(self, command: str | None = None, user_prompt: str | None = None, *, client: OllamaClient | None = None, model: str = "qwen2.5:3b", host: str = "http://localhost:11434",history: list[ChatMessage] | None = None, current_session: ChatSession | None = None, current_profile: UserProfile | None = None, session_manager: SessionManager | None = None, profile_manager: ProfileManager | None = None, artifact_manager: ArtifactManager | None = None, current_persona: Persona | None = None, persona_manager: PersonaManager | None = None, versioning_engine: PromptVersioningEngine | None = None, max_tokens: int = 2000, rag_enabled: bool = False, structured_mode: bool = False, active_tools: Any = None, tools_enabled: bool = False, mcp_client: MCPClient | None = None, mcp_tool_names: list[str] | None = None,) -> None:
        """Initialise le routeur de commandes interactives avec le contexte d'exécution.
                PARAMS: - command - STR | NONE: nom de la commande invoquée
                        - user_prompt - STR | NONE: ligne de commande utilisateur complète
                        - client - OLLAMACLIENT | NONE: client HTTP Ollama actif
                        - model - STR: nom du modèle Ollama
                        - host - STR: URL du serveur Ollama
                        - history - LIST[CHATMESSAGE] | NONE: historique des messages en cours
                        - current_session - CHATSESSION | NONE: session courante
                        - current_profile - USERPROFILE | NONE: profil utilisateur actif
                        - session_manager - SESSIONMANAGER | NONE: gestionnaire de sessions
                        - profile_manager - PROFILEMANAGER | NONE: gestionnaire de profils
                        - artifact_manager - ARTIFACTMANAGER | NONE: gestionnaire de livrables
                        - current_persona - PERSONA | NONE: persona active
                        - persona_manager - PERSONAMANAGER | NONE: gestionnaire de personas
                        - versioning_engine - PROMPTVERSIONINGENGINE | NONE: moteur de versioning
                        - max_tokens - INT: budget maximal de jetons de contexte
                        - rag_enabled - BOOL: activation de l'enrichissement RAG
                        - structured_mode - BOOL: activation du mode JSON structuré
                        - active_tools - ANY: registre d'outils actif
                        - tools_enabled - BOOL: activation du support des outils
                        - mcp_client - MCPCLIENT | NONE: client MCP connecté
                        - mcp_tool_names - LIST[STR] | NONE: liste des noms d'outils MCP enregistrés
                RETURN: None"""
        self.command: str = command or ""
        self.user_prompt: str = user_prompt or ""
        self.client = client
        self.model = model or "qwen2.5:3b"
        self.host = host
        self.history = history if history is not None else []
        self.current_session = current_session
        self.current_profile = current_profile
        self.session_manager = session_manager
        self.profile_manager = profile_manager
        self.artifact_manager = artifact_manager
        self.versioning_engine = versioning_engine if versioning_engine is not None else default_versioning_engine
        self.persona_manager = persona_manager if persona_manager is not None else PersonaManager(versioning_engine=self.versioning_engine)
        self.current_persona = current_persona
        self.max_tokens = max_tokens
        self.rag_enabled = rag_enabled
        self.structured_mode = structured_mode
        self.active_tools = active_tools
        self.tools_enabled = tools_enabled
        self.mcp_client = mcp_client
        self.mcp_tool_names = mcp_tool_names if mcp_tool_names is not None else []

    @property
    def commands_dict(self) -> dict[str, Callable[[str], None]]:
        """Retourne la table de correspondance associant chaque slash-commande à sa méthode exécutable.
                PARAMS: Aucun
                RETURN: dictionnaire associant commandes et callbacks exécutables"""
        return {
            k: (lambda prompt="", f=fn: f(self, prompt))
            for k, fn in COMMANDS_DICT.items()
        }

    @classmethod
    def check_command(cls, user_prompt: str) -> str | None:
        """Détecte si l'entrée utilisateur correspond à une commande répertoriée.
                PARAMS: - user_prompt - STR: texte saisi par l'utilisateur
                RETURN: nom de la commande reconnue ou None"""
        if not user_prompt:
            return None
        cmd = user_prompt.split(maxsplit=1)[0].lower()
        if cmd in COMMANDS_LIST:
            return cmd
        return None

    def execute_command(self, command: str, user_prompt: str | None = None) -> bool:
        """Route et exécute la commande correspondante.
                PARAMS: - command - STR: nom ou identifiant de la commande
                        - user_prompt - STR | NONE: invite complète saisie par l'utilisateur
                RETURN: False si l'application doit quitter, True sinon"""
        if user_prompt is None:
            user_prompt = command
        cmd_key = command.lower()
        if cmd_key in ("/exit", "/quit"):
            self.exit_app(user_prompt)
            return False

        handler = COMMANDS_DICT.get(cmd_key)
        if handler:
            handler(self, user_prompt)
            return True

        print(f"Command '{command}' not found.")
        return True

    def print_help(self, user_prompt: str = "") -> None:
        """Affiche dans la console l'ensemble des commandes spéciales disponibles dans la session.
                PARAMS: - user_prompt - STR: arguments textuels optionnels de la commande
                RETURN: None"""
        print("\nAvailable commands:")
        print("  /help                     : Display this help message")
        print("  /clear                    : Reset session history")
        print("  /history                  : Display the number of exchanged messages")
        print("  /budget                   : Display the number of consumed tokens")
        print("  /rag [on|off]             : Enable or disable RAG document enrichment")
        print("  /debug [on|off]           : Enable or disable debug logs and traces")
        print("  /clear-cache              : Flush the entire vector semantic cache")
        print("  /session list             : List saved sessions")
        print("  /session load <id>        : Load a past session and its history")
        print("  /session new [title]      : Initialize a new blank session")
        print("  /session delete <id>      : Delete an existing session")
        print("  /profile show             : Display active user profile details")
        print("  /profile load <name>      : Switch to another user profile")
        print("  /persona [list|<name>]    : List or activate a persona without clearing history")
        print("  /prompt versions <name>   : Display prompt version history for a persona")
        print("  /prompt diff <name> <v1> <v2> : Compare two versions of a prompt")
        print("  /prompt rollback <name> <v>   : Restore a previous version of a persona")
        print("  /models                   : List models installed on Ollama server")
        print("  /model [name]             : Display or change active model without restart")
        print("  /tools [on|off]           : List available tools or enable/disable tool calling")
        print("  /mcp [status|connect|disconnect] : Manage connection to external MCP server")
        print("  /kingdom [name]           : Generate kingdom details in strict JSON format")
        print("  /figure [name]            : Generate historical figure details in strict JSON format")
        print("  /structured-output [on|off] : Enable or disable JSON structured mode")
        print("  /artifact [reset|save [path]] : Display, reset or export session artifact")
        print("  /export [pdf|md] [path]   : Export conversation or artifact as PDF or Markdown")
        print("  /simulation               : Enter in the simulation mode of the agent")
        print("  /encyclopedia             : Enter in the encyclopedia mode of the agent")
        print("  /exit | /quit             : Exit the application\n")

    def _apply_persona_to_history(self, persona: Persona) -> None:
        """Met à jour le prompt système dans l'historique sans effacer les messages échangés.
                PARAMS: - persona - PERSONA: persona dont les consignes doivent être injectées
                RETURN: None"""
        new_system_content = persona.system_prompt
        if self.tools_enabled and "update_artifact" not in new_system_content:
            new_system_content = f"{new_system_content}\n\n{ARTIFACT_SYSTEM_INSTRUCTION}"

        if self.history and self.history[0].role == "system":
            self.history[0] = ChatMessage(role="system", content=new_system_content)
        else:
            self.history.insert(0, ChatMessage(role="system", content=new_system_content))

        if self.current_session:
            self.current_session.messages = list(self.history)
            if self.session_manager:
                self.session_manager.save_session(self.current_session)

    def clear_screen(self, user_prompt: str = "") -> None:
        """Réinitialise l'historique de la session en mémoire et sur disque.
                PARAMS: - user_prompt - STR: arguments optionnels de la commande
                RETURN: None"""
        self.history.clear()
        singleton_token.context_tokens = 0
        singleton_token.budget_tokens = 0
        if self.current_persona:
            self._apply_persona_to_history(self.current_persona)
        elif self.current_profile:
            self.history.append(ChatMessage(role="system", content=self.current_profile.format_system_prompt()))
        if self.current_session:
            self.current_session.messages = list(self.history)
            self.current_session.metadata.context_tokens = 0
            self.current_session.metadata.total_tokens = 0
            if self.session_manager:
                self.session_manager.save_session(self.current_session)
        print("[Info] Session history reset.")

    def print_history(self, user_prompt: str = "") -> None:
        """Affiche le nombre de messages stockés dans l'historique de la session.
                PARAMS: - user_prompt - STR: arguments optionnels de la commande
                RETURN: None"""
        sess_id = self.current_session.metadata.session_id if self.current_session else "N/A"
        print(f"[Info] Current history : {len(self.history)} message(s) in memory (Session: {sess_id}).")

    def print_budget(self, user_prompt: str = "") -> None:
        """Affiche le nombre de tokens consommés par rapport au budget alloué.
                PARAMS: - user_prompt - STR: arguments optionnels de la commande
                RETURN: None"""
        print(f"[Info] Token budget : {singleton_token.budget_tokens} / {self.max_tokens} consumed.")

    def switch_rag(self, user_prompt: str = "") -> None:
        """Active, désactive ou bascule l'enrichissement documentaire RAG.
                PARAMS: - user_prompt - STR: argument d'état optionnel ('on' ou 'off')
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else None
        if arg in ("on", "true", "1", "enable"):
            self.rag_enabled = True
            print("[Info] Vector RAG enrichment enabled.")
        elif arg in ("off", "false", "0", "disable"):
            self.rag_enabled = False
            print("[Info] Vector RAG enrichment disabled.")
        else:
            self.rag_enabled = not self.rag_enabled
            status = "enabled" if self.rag_enabled else "disabled"
            print(f"[Info] Vector RAG enrichment {status}.")

    def switch_debug(self, user_prompt: str = "") -> None:
        """Active, désactive ou affiche le statut du mode debug.
                PARAMS: - user_prompt - STR: argument d'état optionnel ('on' ou 'off')
                RETURN: None"""
        parts = user_prompt.strip().split(maxsplit=1)
        if len(parts) == 2:
            sub = parts[1].strip().lower()
            if sub in ("on", "1", "true", "enable"):
                set_debug(True)
                print("[Info] Debug mode enabled.")
            elif sub in ("off", "0", "false", "disable"):
                set_debug(False)
                print("[Info] Debug mode disabled.")
            else:
                print("[Usage] /debug [on|off]")
        else:
            print(f"[Info] Debug mode is currently {'ON' if is_debug() else 'OFF'}.")

    def clear_cache_command(self, user_prompt: str = "") -> None:
        """Purge le cache sémantique vectoriel de Qdrant.
                PARAMS: - user_prompt - STR: arguments optionnels
                RETURN: None"""
        from src.core import sementic_cache
        try:
            sementic_cache.clean_cache()
            print("[Info] Cache cleared successfully!")
        except Exception as exc:
            print(f"[Error clearing cache] {exc}")

    def switch_mcp(self, user_prompt: str = "") -> None:
        """Gère le cycle de vie de la connexion à un serveur MCP externe.
                PARAMS: - user_prompt - STR: sous-commande MCP ('status', 'connect <cmd>', 'disconnect')
                RETURN: None"""
        parts = user_prompt.split(maxsplit=2)
        subcmd = parts[1].strip().lower() if len(parts) > 1 else "status"
        if subcmd == "status":
            if self.mcp_client and self.mcp_client.is_connected:
                tools = self.mcp_client.list_tools()
                print(f"[Info] Connected MCP server : {' '.join(self.mcp_client.command)}")
                print(f"[Info] Exposed MCP tools ({len(tools)}) : {', '.join(t.name for t in tools)}")
            else:
                print("[Info] No external MCP server connected.")
        elif subcmd == "connect":
            if len(parts) < 3 or not parts[2].strip():
                print("[Info] Usage : /mcp connect <server_command> (e.g.: /mcp connect python -m src.features.tools.mcp_server_demo)")
            else:
                cmd_str = parts[2].strip()
                try:
                    if self.mcp_client:
                        default_registry.unregister_tools(self.mcp_tool_names)
                        self.mcp_client.close()
                    self.mcp_client = MCPClient(cmd_str)
                    self.mcp_client.start()
                    mcp_defs = default_registry.register_mcp_client(self.mcp_client)
                    self.mcp_tool_names = [d.name for d in mcp_defs]
                    self.active_tools = default_registry
                    print(f"[Info] MCP server connected successfully. {len(mcp_defs)} tool(s) registered : {', '.join(self.mcp_tool_names)}")
                except Exception as exc:
                    print(f"[MCP Error] Failed to connect server : {exc}")
        elif subcmd in ("disconnect", "stop", "close"):
            if self.mcp_client:
                default_registry.unregister_tools(self.mcp_tool_names)
                self.mcp_tool_names.clear()
                self.mcp_client.close()
                self.mcp_client = None
                print("[Info] MCP server disconnected and its tools have been removed.")
            else:
                print("[Info] No MCP server was connected.")
        else:
            print("[Info] Available /mcp subcommands : status, connect <cmd>, disconnect")

    def manage_session(self, user_prompt: str = "") -> None:
        """Gère la création, le listage, le rechargement et la suppression des sessions.
                PARAMS: - user_prompt - STR: sous-commande ('list', 'load <id>', 'new [titre]', 'delete <id>')
                RETURN: None"""
        if self.session_manager is None:
            print("[Error] Session manager unavailable.")
            return
        parts = user_prompt.split(maxsplit=2)
        subcmd = parts[1].strip().lower() if len(parts) > 1 else "list"
        if subcmd == "list":
            sessions = self.session_manager.list_sessions()
            if not sessions:
                print("[Info] No saved sessions.")
            else:
                print(f"[Info] Saved sessions ({len(sessions)}) :")
                current_id = self.current_session.metadata.session_id if self.current_session else ""
                for s in sessions:
                    active_mark = " (active)" if s.session_id == current_id else ""
                    source_tag = f" [{s.source}]" if getattr(s, "source", "local") != "local" else ""
                    print(f"  - [{s.session_id[:8]}] {s.title} (Model: {s.model}, Updated: {s.updated_at[:19]}){source_tag}{active_mark}")
        elif subcmd == "load":
            if len(parts) < 3 or not parts[2].strip():
                print("[Info] Usage : /session load <id>")
            else:
                target_id = parts[2].strip()
                try:
                    self.current_session = self.session_manager.load_session(target_id)
                    self.history.clear()
                    self.history.extend(self.current_session.messages)
                    c_toks = getattr(getattr(self.current_session, "metadata", None), "context_tokens", 0)
                    singleton_token.context_tokens = c_toks if isinstance(c_toks, (int, float)) else 0
                    t_toks = getattr(getattr(self.current_session, "metadata", None), "total_tokens", 0)
                    singleton_token.budget_tokens = t_toks if isinstance(t_toks, (int, float)) else 0
                    if self.current_session.metadata.model:
                        self.model = self.current_session.metadata.model
                    if self.artifact_manager:
                        current_artifact = self.artifact_manager.get_or_create_artifact(self.current_session.metadata.session_id)
                        set_active_artifact(current_artifact, session_id=self.current_session.metadata.session_id, manager=self.artifact_manager)
                    print(f"[Info] Session '{target_id}' loaded successfully ({len(self.history)} messages, model: {self.model}).")
                except FileNotFoundError:
                    print(f"[Error] Session '{target_id}' not found.")
        elif subcmd == "new":
            if self.current_session and not any(m.role in ("user", "assistant") for m in self.current_session.messages):
                self.session_manager.delete_session(self.current_session.metadata.session_id)
            title_arg = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
            self.current_session = self.session_manager.create_session(profile=self.current_profile, model=self.model, title=title_arg)
            self.history.clear()
            self.history.extend(self.current_session.messages)
            singleton_token.context_tokens = 0
            singleton_token.budget_tokens = 0
            if self.artifact_manager:
                current_artifact = self.artifact_manager.get_or_create_artifact(self.current_session.metadata.session_id)
                set_active_artifact(current_artifact, session_id=self.current_session.metadata.session_id, manager=self.artifact_manager)
            print(f"[Info] New session initialized : [{self.current_session.metadata.session_id}] {self.current_session.metadata.title}.")
        elif subcmd in ("delete", "remove", "rm"):
            if len(parts) < 3 or not parts[2].strip():
                print("[Info] Usage : /session delete <id>")
            else:
                target_id = parts[2].strip()
                if self.session_manager.delete_session(target_id):
                    print(f"[Info] Session '{target_id}' deleted.")
                    if self.current_session and self.current_session.metadata.session_id == target_id:
                        self.current_session = self.session_manager.create_session(profile=self.current_profile, model=self.model)
                        self.history.clear()
                        self.history.extend(self.current_session.messages)
                        singleton_token.context_tokens = 0
                        singleton_token.budget_tokens = 0
                        if self.artifact_manager:
                            current_artifact = self.artifact_manager.get_or_create_artifact(self.current_session.metadata.session_id)
                            set_active_artifact(current_artifact, session_id=self.current_session.metadata.session_id, manager=self.artifact_manager)
                        print(f"[Info] Active session reset : [{self.current_session.metadata.session_id}].")
                else:
                    print(f"[Error] Session '{target_id}' not found.")
        else:
            print("[Info] Available /session commands : list, load <id>, new [title], delete <id>")

    def manage_profile(self, user_prompt: str = "") -> None:
        """Affiche, liste ou change le profil utilisateur actif.
                PARAMS: - user_prompt - STR: sous-commande ('show', 'load <nom>', 'list')
                RETURN: None"""
        if self.profile_manager is None:
            print("[Error] Profile manager unavailable.")
            return
        parts = user_prompt.split(maxsplit=2)
        subcmd = parts[1].strip().lower() if len(parts) > 1 else "show"
        if subcmd == "show":
            if self.current_profile:
                print(f"[User Profile : {self.current_profile.username}]")
                print(f"  - Style and tone : {self.current_profile.tone}")
                print(f"  - Conciseness    : {self.current_profile.conciseness}")
                print(f"  - Language       : {self.current_profile.language}")
                if self.current_profile.custom_instructions:
                    print(f"  - Instructions   : {self.current_profile.custom_instructions}")
                if self.current_profile.facts:
                    print(f"  - Known facts    : {', '.join(self.current_profile.facts)}")
            else:
                print("[Info] No specific profile loaded in this session.")
        elif subcmd in ("load", "switch"):
            if len(parts) < 3 or not parts[2].strip():
                print("[Info] Usage : /profile load <name>")
            else:
                target_name = parts[2].strip()
                self.current_profile = self.profile_manager.get_or_create_profile(target_name)
                print(f"[Info] Profile '{self.current_profile.username}' loaded.")
        elif subcmd == "list":
            profiles = self.profile_manager.list_profiles()
            print(f"[Info] Existing profiles ({len(profiles)}) : {', '.join(profiles) if profiles else 'None'}")
        else:
            print("[Info] Available /profile commands : show, load <name>, list")

    def print_models(self, user_prompt: str = "") -> None:
        """Affiche la liste des modèles installés sur le serveur Ollama.
                PARAMS: - user_prompt - STR: arguments optionnels de la commande
                RETURN: None"""
        if not self.client:
            print("[Error] Ollama client not initialized.")
            return
        try:
            models = self.client.list_models()
            print(f"[Info] Available models ({len(models)}) : {', '.join(models) if models else 'None'}")
        except OllamaError as err:
            print(f"[Error] {err}")

    def switch_model(self, user_prompt: str = "") -> None:
        """Affiche ou modifie le nom du modèle actif en session.
                PARAMS: - user_prompt - STR: nom du nouveau modèle à affecter
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            self.model = parts[1].strip()
            if self.current_session:
                self.current_session.metadata.model = self.model
                if self.session_manager:
                    self.session_manager.save_session(self.current_session)
            print(f"[Info] Active model updated : {self.model}")
        else:
            print(f"[Info] Currently selected model : {self.model}")
            print("[Tip] To change: /model <model_name> (e.g.: /model llama3)")

    def print_tools(self, user_prompt: str = "") -> None:
        """Affiche la liste des outils ou active/désactive le mode tool calling.
                PARAMS: - user_prompt - STR: option d'activation ('on' ou 'off')
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        sub = parts[1].strip().lower() if len(parts) > 1 else ""
        if sub in ("on", "1", "enable", "activer"):
            self.active_tools = default_registry
            print("[Info] MCP tools enabled for this session.")
        elif sub in ("off", "0", "disable", "desactiver", "désactiver"):
            self.active_tools = None
            print("[Info] MCP tools disabled for this session.")
        else:
            registered = default_registry.list_tools()
            print(f"[Info] Registered tools ({len(registered)}) :")
            for t in registered:
                print(f"  - {t.name}: {t.description}")
            print(f"[Info] Current status : {'Enabled' if self.active_tools is not None else 'Disabled'}")

    def enable_structured_output(self, user_prompt: str = "") -> None:
        """Active ou désactive le mode JSON structuré de la session.
                PARAMS: - user_prompt - STR: bascule ('on', 'off') ou vide pour inverser l'état
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None

        if arg is None:
            self.structured_mode = not self.structured_mode
            status = "enabled" if self.structured_mode else "disabled"
            print(f"[Info] Structured output mode {status}. (Format: {{\"response\": ...}})")
            return

        if arg.lower() in ("on", "true", "1", "enable", "activer"):
            self.structured_mode = True
            print("[Info] Structured output mode enabled. (Format: {\"response\": ...})")
            return

        if arg.lower() in ("off", "false", "0", "disable", "desactiver", "désactiver"):
            self.structured_mode = False
            print("[Info] Structured output mode disabled.")
            return

        print(
            "[Info] /structured-output is a mode switch. Usage: /structured-output [on|off]. "
            "Enable it and ask your question directly in the chat to benefit from RAG and history."
        )

    def manage_artifact(self, user_prompt: str = "") -> None:
        """Affiche, réinitialise ou sauvegarde le livrable Markdown d'état.
                PARAMS: - user_prompt - STR: sous-commande ('show', 'reset', 'save [path]')
                RETURN: None"""
        parts = user_prompt.split(maxsplit=2)
        subcmd = parts[1].strip().lower() if len(parts) > 1 else "show"
        if subcmd == "show":
            doc = get_active_artifact()
            if not doc.sections:
                print(f"\n[Artifact : {doc.title}]")
                print("  (Empty artifact for now. Sections will be enriched during exchanges.)")
            else:
                print("\n" + "=" * 60)
                print(f" ARTIFACT — {doc.title}")
                print("=" * 60)
                print(doc.render_markdown().strip())
                print("=" * 60)
        elif subcmd == "reset":
            if self.artifact_manager and self.current_session:
                doc = self.artifact_manager.reset_artifact(self.current_session.metadata.session_id)
                set_active_artifact(doc, session_id=self.current_session.metadata.session_id, manager=self.artifact_manager)
                print(f"[Artifact] Artifact reset for session '{self.current_session.metadata.session_id}'.")
        elif subcmd == "save":
            target_path = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
            doc = get_active_artifact()
            if target_path:
                saved = doc.save(Path(target_path))
                print(f"[Artifact] Artifact exported successfully to '{saved}'.")
            elif self.artifact_manager and self.current_session:
                saved = self.artifact_manager.save_artifact(self.current_session.metadata.session_id, doc)
                print(f"[Artifact] Artifact saved to '{saved}'.")
        else:
            print("[Info] Available /artifact commands : /artifact (display), /artifact reset, /artifact save [path]")

    def manage_export(self, user_prompt: str = "") -> None:
        """Exporte l'historique de conversation ou le livrable actif au format PDF ou Markdown.
                PARAMS: - user_prompt - STR: syntaxe /export [pdf|md] [chemin_optionnel]
                RETURN: None"""
        parts = user_prompt.strip().split(maxsplit=2)
        format_type = parts[1].lower() if len(parts) > 1 else "pdf"
        target_path = parts[2].strip() if len(parts) > 2 else ""

        if format_type not in ("pdf", "md", "markdown"):
            print("[Info] Unrecognized export format. Supported formats: /export pdf [path] or /export md [path]")
            return

        sess_id = (
            self.current_session.metadata.session_id[:8]
            if self.current_session and self.current_session.metadata
            else "session"
        )
        doc = get_active_artifact()
        has_artifact = doc is not None and bool(doc.sections)

        if format_type in ("md", "markdown"):
            default_name = f"export_{sess_id}.md"
            final_path = Path(target_path) if target_path else Path("exports") / default_name
            if final_path.suffix.lower() != ".md":
                final_path = final_path.with_suffix(".md")
            final_path.parent.mkdir(parents=True, exist_ok=True)

            if has_artifact:
                content = doc.render_markdown()
            else:
                lines = [f"# SENSAI Session Report ({sess_id})\n"]
                for msg in self.history:
                    if msg.role == "system" or msg.content.strip().startswith(("/", "You > /")):
                        continue
                    speaker = "**User**" if msg.role == "user" else "**SENSAI Historical Advisor**"
                    lines.append(f"{speaker} :\n{msg.content.strip()}\n")
                content = "\n".join(lines)

            final_path.write_text(content, encoding="utf-8")
            print(f"[Export] Session successfully exported in Markdown to '{final_path}'.")

        elif format_type == "pdf":
            default_name = f"export_{sess_id}.pdf"
            final_path = Path(target_path) if target_path else Path("exports") / default_name

            from src.features.pdf.pdf_generator import export_conversation_to_pdf, generate_pdf

            try:
                if has_artifact:
                    res = generate_pdf(
                        file_path=final_path,
                        title=f"Artifact — {doc.title}",
                        content=doc.render_markdown(),
                        author="SENSAI Historical Advisor",
                    )
                else:
                    res = export_conversation_to_pdf(
                        messages=self.history,
                        file_path=final_path,
                        title="Session Report — SENSAI",
                        author="SENSAI Historical Advisor",
                    )
                print(f"[Export] {res.message}")
            except Exception as exc:
                print(f"[PDF Export Error] {exc}")

    def manage_kingdom(self, user_prompt: str = "") -> None:
        """Génère une fiche de royaume au format JSON strict avec validation historique et support RAG.
                PARAMS: - user_prompt - STR: nom du royaume cible
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        kingdom_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if kingdom_name is None:
            print("[Info] Please specify a kingdom name. Usage : /kingdom [name] (e.g.: /kingdom Qin)")
            return

        kingdom_name, _ = mask_pii(kingdom_name)
        known_kingdoms = {
            "qin", "chu", "qi", "zhao", "wei", "han", "yan",
            "jin", "lu", "song", "zhongshan", "ba", "shu", "yue", "wu", "zhou"
        }
        if kingdom_name.lower() not in known_kingdoms:
            print(f"[Error] '{kingdom_name}' is not a recognized kingdom of the Warring States period.")
            print("Recognized kingdoms include: Qin, Chu, Zhao, Wei, Han, Qi, Yan.")
            return

        if not self.client:
            print("[Error] Ollama client not initialized.")
            return

        print(f"[Info] Generating details for kingdom '{kingdom_name}'...")
        rag_context = ""
        if self.rag_enabled:
            try:
                from src.RAG.retriever import retrieve_rag_context
                rag_res = retrieve_rag_context(
                    f"Kingdom of {kingdom_name} capital ruler military history Warring States",
                    ollama_url=self.host,
                    ollama_model=self.model,
                    fallback_web=True,
                    return_count=False,
                )
                if isinstance(rag_res, tuple):
                    rag_context = rag_res[0] or ""
                elif isinstance(rag_res, str):
                    rag_context = rag_res
            except Exception:
                pass

        system_prompt = (
            "You are a historian specializing in Ancient China's Warring States period. Always respond in English."
        )
        if rag_context:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"HISTORICAL ARCHIVES:\n{rag_context}\n\n"
                "Rely strictly on the historical documents above to produce accurate kingdom details."
            )

        try:
            result = self.client.chat_structured(
                model=self.model,
                messages=[
                    ChatMessage(
                        role="system",
                        content=system_prompt,
                    ),
                    ChatMessage(
                        role="user",
                        content=f"Generate historical details for the kingdom of {kingdom_name}.",
                    ),
                ],
                response_format=KingdomInfo,
            )
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        except OllamaStructuredOutputError as exc:
            print(f"[Structured Output Error] {exc}")
        except OllamaError as exc:
            print(f"[Error] {exc}")

    def manage_figure(self, user_prompt: str = "") -> None:
        """Génère une fiche de personnage historique au format JSON strict avec enrichissement RAG.
                PARAMS: - user_prompt - STR: nom du personnage historique cible
                RETURN: None"""
        parts = user_prompt.split(maxsplit=1)
        figure_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if figure_name is None:
            print("[Info] Please specify a figure name. Usage : /figure [name] (e.g.: /figure Qin Shi Huang)")
            return
        if not self.client:
            print("[Error] Ollama client not initialized.")
            return

        figure_name, _ = mask_pii(figure_name)
        print(f"[Info] Generating details for figure '{figure_name}'...")
        rag_context = ""
        if self.rag_enabled:
            try:
                from src.RAG.retriever import retrieve_rag_context
                rag_res = retrieve_rag_context(
                    f"Historical figure {figure_name} Ancient China Warring States Shiji",
                    ollama_url=self.host,
                    ollama_model=self.model,
                    fallback_web=True,
                    return_count=False,
                )
                if isinstance(rag_res, tuple):
                    rag_context = rag_res[0] or ""
                elif isinstance(rag_res, str):
                    rag_context = rag_res
            except Exception:
                pass

        system_prompt = (
            "You are a historian specializing in the Warring States period and the Qin unification. Always respond in English."
        )
        if rag_context:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"HISTORICAL ARCHIVES:\n{rag_context}\n\n"
                "INSTRUCTIONS:\n"
                "1. Rely strictly on facts from the archives above to complete the biographical record.\n"
                "2. Do not invent fictitious kingdoms, Western rulers (e.g., Caesar), or anachronistic events.\n"
                "3. Accurately identify their origin kingdom, role (général, stratège, légiste, souverain), and key historical achievements."
            )

        try:
            result = self.client.chat_structured(
                model=self.model,
                messages=[
                    ChatMessage(
                        role="system",
                        content=system_prompt,
                    ),
                    ChatMessage(
                        role="user",
                        content=f"Generate historical details for the historical figure {figure_name}.",
                    ),
                ],
                response_format=HistoricalFigure,
            )
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        except OllamaStructuredOutputError as exc:
            print(f"[Structured Output Error] {exc}")
        except OllamaError as exc:
            print(f"[Error] {exc}")

    def manage_persona(self, user_prompt: str = "") -> None:
        """Gère le listage et le basculement dynamique de personas sans perte d'historique.
                PARAMS: - user_prompt - STR: sous-commande ('list', 'defaults', 'load <nom>')
                RETURN: None"""
        if self.persona_manager is None:
            print("[Error] Persona manager not initialized.")
            return

        parts = user_prompt.split(maxsplit=2)
        arg = parts[1].strip() if len(parts) > 1 else ""

        if arg.lower() in ("init", "defaults", "sample", "samples"):
            self.persona_manager.ensure_default_personas()
            personas = self.persona_manager.list_personas()
            print(f"[Info] Sample personas generated ({len(personas)}) : {', '.join(personas)}")
            return

        if not arg or arg.lower() == "list":
            personas = self.persona_manager.list_personas()
            if not personas:
                print("[Info] No personas available in configuration directory.")
            else:
                print(f"[Info] Available personas ({len(personas)}) :")
                for p_name in personas:
                    active_tag = " (active)" if self.current_persona and (
                        self.current_persona.name.lower() == p_name.lower()
                        or (self.current_persona.file_path and self.current_persona.file_path.stem.lower() == p_name.lower())
                    ) else ""
                    print(f"  - {p_name}{active_tag}")
            if self.current_persona:
                print(f"[Info] Active persona : {self.current_persona.name} (v{self.current_persona.active_version})")
            else:
                print("[Info] No active persona (standard profile).")
            return


        target_name = parts[2].strip() if arg.lower() in ("load", "switch", "set") and len(parts) > 2 else arg
        try:
            persona = self.persona_manager.load_persona(target_name)
            self.current_persona = persona
            self._apply_persona_to_history(persona)
            print(f"[Info] Persona '{persona.name}' activated (Version: v{persona.active_version}). History ({len(self.history)} message(s)) preserved.")
        except Exception as exc:
            print(f"[Persona Error] {exc}")

    def manage_prompt(self, user_prompt: str = "") -> None:
        """Gère le versioning, l'inspection de diff et le rollback des personas.
                PARAMS: - user_prompt - STR: sous-commande ('versions', 'diff', 'rollback')
                RETURN: None"""
        parts = user_prompt.split()
        if len(parts) < 2:
            print("[Info] Usage of /prompt command :")
            print("  /prompt versions <name>       : Display version history of a persona")
            print("  /prompt diff <name> <v1> <v2> : Display unified diff between two versions")
            print("  /prompt rollback <name> <v>   : Restore a previous version")
            return

        subcmd = parts[1].lower()
        if subcmd in ("versions", "history", "log"):
            if len(parts) < 3:
                if self.current_persona:
                    persona_name = self.current_persona.file_path.stem if self.current_persona.file_path else self.current_persona.name
                else:
                    print("[Info] Usage : /prompt versions <persona_name>")
                    return
            else:
                persona_name = parts[2]

            history = self.versioning_engine.get_history(persona_name)
            if not history:
                print(f"[Info] No versions recorded for '{persona_name}'.")
                return
            print(f"[Info] Version history for '{persona_name}' ({len(history)} version(s)) :")
            for v in history:
                msg_suffix = f" — {v.message}" if v.message else ""
                print(f"  - v{v.version} [{v.timestamp[:19]}] (hash: {v.content_hash[:8]}) by {v.author}{msg_suffix}")

        elif subcmd == "diff":
            if len(parts) < 5:
                print("[Info] Usage : /prompt diff <name> <v1> <v2> (e.g.: /prompt diff scribe_qin 1 2)")
                return
            persona_name = parts[2]
            v_from = parts[3]
            v_to = parts[4]
            try:
                diff_text = self.versioning_engine.get_diff(persona_name, v_from, v_to)
                if not diff_text:
                    print(f"[Info] No textual differences between version {v_from} and version {v_to}.")
                else:
                    print(f"\n--- Diff {persona_name} : v{v_from} -> v{v_to} ---")
                    print(diff_text.strip())
                    print("-" * 50)
            except Exception as exc:
                print(f"[Prompt Diff Error] {exc}")

        elif subcmd == "rollback":
            if len(parts) < 4:
                print("[Info] Usage : /prompt rollback <name> <v> (e.g.: /prompt rollback scribe_qin 1)")
                return
            persona_name = parts[2]
            target_v = parts[3]
            try:
                _restored = self.versioning_engine.rollback(persona_name, target_v)
                if self.current_persona and (
                    (self.current_persona.file_path and self.current_persona.file_path.stem.lower() == persona_name.lower())
                    or self.current_persona.name.lower() == persona_name.lower()
                ):
                    updated = self.persona_manager.load_persona(persona_name)
                    self.current_persona = updated
                    self._apply_persona_to_history(updated)
                print(f"[Info] Persona '{persona_name}' restored to version {target_v} successfully.")
            except Exception as exc:
                print(f"[Rollback Error] {exc}")
        else:
            print(f"[Info] Unknown /prompt subcommand : '{subcmd}'. Options : versions, diff, rollback.")

    def exit_app(self, user_prompt: str = "") -> None:
        """Affiche le message de sortie de session.
                PARAMS: - user_prompt - STR: arguments optionnels
                RETURN: None"""
        print("Exiting SENSAI.")


Command = Commands
command = Commands

COMMANDS_DICT: dict[str, Any] = {
    "/help": Commands.print_help,
    "/clear": Commands.clear_screen,
    "/history": Commands.print_history,
    "/budget": Commands.print_budget,
    "/rag": Commands.switch_rag,
    "/debug": Commands.switch_debug,
    "/clear-cache": Commands.clear_cache_command,
    "/clearcache": Commands.clear_cache_command,
    "/mcp": Commands.switch_mcp,
    "/session": Commands.manage_session,
    "/sessions": Commands.manage_session,
    "/profile": Commands.manage_profile,
    "/persona": Commands.manage_persona,
    "/personas": Commands.manage_persona,
    "/prompt": Commands.manage_prompt,
    "/prompts": Commands.manage_prompt,
    "/models": Commands.print_models,
    "/model": Commands.switch_model,
    "/tools": Commands.print_tools,
    "/structured-output": Commands.enable_structured_output,
    "/structured_output": Commands.enable_structured_output,
    "/artifact": Commands.manage_artifact,
    "/artifacts": Commands.manage_artifact,
    "/export": Commands.manage_export,
    "/kingdom": Commands.manage_kingdom,
    "/kingdoms": Commands.manage_kingdom,
    "/figure": Commands.manage_figure,
    "/figures": Commands.manage_figure,
    "/exit": Commands.exit_app,
    "/quit": Commands.exit_app,
}