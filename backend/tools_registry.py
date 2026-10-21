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
from src.features.tools import builtin, web_search  # noqa: E402,F401  (enregistrent les outils)

# "Structured Output" n'est pas un outil appelé par le modèle : c'est un mode de réponse (JSON)
STRUCTURED_OUTPUT_IDS = ("structured_output", "Structured Output")
# Ancien identifiant du frontend : active tous les outils du registre
ALL_TOOLS_ID = "mcp_runner"

_executor = ToolExecutor(registry=default_registry)

# Présentation côté interface (icône lucide + catégorie), purement cosmétique
_TOOL_UI = {
    "web_search": ("Globe", "Web"),
    "search_historical_archives": ("BookOpen", "Histoire de Chine"),
    "get_kingdom_info": ("Database", "Histoire de Chine"),
    "query_kingdom_database": ("Database", "Base de données"),
    "update_kingdom_database": ("Database", "Base de données"),
    "read_manuscript_file": ("FileText", "Manuscrits"),
    "write_manuscript_file": ("FileText", "Manuscrits"),
}

_STRUCTURED_OUTPUT_INFO = {
    "id": "structured_output",
    "name": "Structured Output",
    "description": "Formate et génère une sortie au format JSON structuré strict [T5].",
    "parameters": {},
    "icon": "Code",
    "category": "Développement",
}


def list_tools() -> List[Dict[str, Any]]:
    tools = [dict(_STRUCTURED_OUTPUT_INFO)]
    for tool_def in default_registry.list_tools():
        icon, category = _TOOL_UI.get(tool_def.name, ("Wrench", "Outils"))
        tools.append({
            "id": tool_def.name,
            "name": tool_def.name.replace("_", " ").capitalize(),
            "description": tool_def.description.split("\n")[0].strip(),
            "parameters": tool_def.parameters.get("properties", {}),
            "icon": icon,
            "category": category,
        })
    return tools


def selected_tool_names(enabled_ids: List[str]) -> List[str]:
    """Noms des outils du registre activés par la liste d'identifiants du frontend."""
    registry_names = [t.name for t in default_registry.list_tools()]
    if ALL_TOOLS_ID in enabled_ids:
        return registry_names
    return [name for name in registry_names if name in enabled_ids]


def get_ollama_tools(enabled_ids: List[str]) -> List[Dict[str, Any]]:
    names = set(selected_tool_names(enabled_ids))
    return [t.to_ollama_dict() for t in default_registry.list_tools() if t.name in names]


def run_tool(tool_id: str, args: Dict[str, Any]) -> str:
    return _executor.execute(tool_id, args or {}).to_tool_message_content()
