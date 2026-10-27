"""Pont entre le backend web et le registre d'outils partagé avec le CLI.

Aucun outil n'est (ré)implémenté ici : ils vivent dans src/features/tools et sont
simplement listés puis appelés via le registre par défaut, comme dans le CLI.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Rend le package `src` importable (racine du dépôt, ou /app dans le conteneur)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.features.tools import ToolExecutor, default_registry  # noqa: E402
from src.features.tools import builtin, forms, web_search  # noqa: E402,F401  (enregistrent les outils)
from src.features.tools.forms import normalize_form  # noqa: E402,F401
from src.features.tools.mcp_client import MCPClient, MCPError  # noqa: E402,F401
from src.core.fs_tools import (  # noqa: E402
    clear_action_confirmations,
    register_action_confirmation,
    set_confirmation_callback,
)

# "Structured Output" n'est pas un outil appelé par le modèle : c'est un mode de réponse (JSON)
STRUCTURED_OUTPUT_IDS = ("structured_output", "Structured Output")
# Ancien identifiant du frontend : active tous les outils du registre
ALL_TOOLS_ID = "mcp_runner"
# Outil interactif : sur le web, l'appel n'est pas exécuté, il devient un formulaire affiché à l'utilisateur
FORM_TOOL_NAME = "ask_user_form"
FORM_BLOCK_LANG = "sensai-form"
CONFIRM_BLOCK_LANG = "sensai-confirm"
DESTRUCTIVE_TOOLS = {"write_manuscript_file", "update_kingdom_database"}
# Outils internes actifs par défaut pour l'IA, masqués dans les contrôles utilisateur
INTERNAL_TOOLS = {FORM_TOOL_NAME}

_executor = ToolExecutor(registry=default_registry)

# Présentation côté interface (icône lucide + catégorie), purement cosmétique
_TOOL_UI = {
    "web_search": ("Globe", "Web"),
    "search_historical_archives": ("BookOpen", "Histoire de Chine"),
    "get_kingdom_info": ("Landmark", "Histoire de Chine"),
    "query_kingdom_database": ("Database", "Base de données"),
    "update_kingdom_database": ("DatabaseZap", "Base de données"),
    "read_manuscript_file": ("FileText", "Manuscrits"),
    "write_manuscript_file": ("FilePen", "Manuscrits"),
    "ask_user_form": ("ListChecks", "Interaction"),
    "calculate_grain_supply": ("Wrench", "Logistique MCP"),
    "get_historical_battle": ("BookOpen", "Batailles MCP"),
}

_STRUCTURED_OUTPUT_INFO = {
    "id": "structured_output",
    "name": "Structured Output",
    "description": "Formate et génère une sortie au format JSON structuré strict [T5].",
    "parameters": {},
    "icon": "Code",
    "category": "Développement",
}


def register_mcp_client(client: MCPClient, prefix: str = "") -> List[str]:
    """Enregistre les outils d'un MCPClient dans default_registry et renvoie la liste de leurs noms."""
    defs = default_registry.register_mcp_client(client, prefix=prefix)
    return [d.name for d in defs]


def unregister_mcp_tools(tool_names: List[str]) -> None:
    """Retire les outils spécifiés du default_registry."""
    default_registry.unregister_tools(tool_names)


def list_tools() -> List[Dict[str, Any]]:
    tools = [dict(_STRUCTURED_OUTPUT_INFO, visible=True)]
    for tool_def in default_registry.list_tools():
        icon, category = _TOOL_UI.get(
            tool_def.name,
            ("Wrench", "MCP" if "mcp" in tool_def.name.lower() else "Outils"),
        )
        is_visible = tool_def.name not in INTERNAL_TOOLS
        tools.append({
            "id": tool_def.name,
            "name": tool_def.name.replace("_", " ").capitalize(),
            "description": tool_def.description.split("\n")[0].strip(),
            "parameters": tool_def.parameters.get("properties", {}),
            "icon": icon,
            "category": category,
            "visible": is_visible,
        })
    return tools


def selected_tool_names(enabled_ids: List[str]) -> List[str]:
    """Noms des outils du registre activés par la liste d'identifiants du frontend."""
    registry_names = [t.name for t in default_registry.list_tools()]
    if ALL_TOOLS_ID in enabled_ids:
        return registry_names
    selected = [name for name in registry_names if name in enabled_ids]
    for internal_name in INTERNAL_TOOLS:
        if internal_name in registry_names and internal_name not in selected:
            selected.append(internal_name)
    return selected


def get_ollama_tools(enabled_ids: List[str]) -> List[Dict[str, Any]]:
    names = set(selected_tool_names(enabled_ids))
    return [t.to_ollama_dict() for t in default_registry.list_tools() if t.name in names]


def run_tool(tool_id: str, args: Dict[str, Any]) -> str:
    return _executor.execute(tool_id, args or {}).to_tool_message_content()


def build_form_block(args: Dict[str, Any]) -> str:
    """Bloc markdown décrivant le formulaire, rendu par le frontend (ValueError si invalide)."""
    form = normalize_form((args or {}).get("title"), (args or {}).get("questions"))
    return f"\n```{FORM_BLOCK_LANG}\n{json.dumps(form, ensure_ascii=False)}\n```\n"


def build_confirm_block(
    summary: str,
    tool_name: str = "",
    action_id: str = "",
    action_type: str = "",
    details: Any = None,
) -> str:
    """Bloc markdown décrivant une demande de confirmation humaine (style sensai-confirm)."""
    payload = {
        "summary": summary,
        "tool_name": tool_name,
        "action_id": action_id,
        "action_type": action_type or ("file_write" if "file" in tool_name else "db_update"),
        "details": details or {},
    }
    return f"\n```{CONFIRM_BLOCK_LANG}\n{json.dumps(payload, ensure_ascii=False)}\n```\n"
