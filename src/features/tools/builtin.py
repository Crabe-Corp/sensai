import json
from typing import Any

from src.features.tools.registry import tool

@tool
def search_historical_archives(query: str) -> dict[str, Any]:
    """Recherche des chroniques et extraits historiques pertinents dans les archives (RAG vectoriel).
            PARAMS: - query - STR: question ou mots-clés historiques à rechercher
            RETURN: dictionnaire contenant les extraits des sources d'époque trouvées"""

    try:
        from src.RAG.retriever import retrieve_rag_context

        context = retrieve_rag_context(query)
        if context:
            return {"status": "success", "context": context}
        return {"status": "empty", "message": "Aucun document historique trouvé pour cette requête."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
