from typing import Any
from src.core.db.database import get_active_diplomacy, get_kingdom_stats
from src.features.tools.registry import tool


@tool
def get_kingdom_info(kingdom_name: str) -> dict[str, Any]:
    """Récupère les informations complètes d'un royaume incluant ses statistiques et ses relations diplomatiques.
            PARAMS: - kingdom_name - STR: le nom du royaume à consulter
            RETURN: dictionnaire contenant les statistiques et relations du royaume, ou une erreur"""
    stats = get_kingdom_stats(kingdom_name)
    if "error" in stats:
        return stats

    diplomacy = get_active_diplomacy(kingdom_name)
    if "error" not in diplomacy:
        stats["relations"] = diplomacy.get("relations", [])
    return stats
