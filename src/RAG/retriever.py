import json
import logging
import requests
from typing import Any

from src.RAG.RAG_embedding import COLLECTION_NAME, get_embedding, get_bm25_model

logger = logging.getLogger(__name__)


def extract_character(prompt: str, ollama_url: str = "http://localhost:11434", ollama_model: str = "qwen2.5:1.5b") -> str | None:
    """Extrait le nom du personnage historique principal mentionné dans la question.
            PARAMS: - prompt - STR: texte de la requête utilisateur
                    - ollama_url - STR: adresse racine du serveur Ollama
            RETURN: nom extrait du personnage ou None"""

    system_prompt = (
        "Tu es un extracteur d'entités. Ton seul but est d'analyser la question de l'utilisateur "
        "et d'extraire le nom du personnage historique principal mentionné.\n"
        "Retourne UNIQUEMENT un JSON strict.\n"
        "Si un personnage est trouvé : {\"personnage\": \"Nom du personnage\"}\n"
    )
    try:
        response = requests.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json={
                "model": ollama_model,
                "prompt": f"{system_prompt}\nQuestion : {prompt}",
                "stream": False,
                "format": "json",
            },
            timeout=5.0,
        )
        if response.status_code == 200:
            data = response.json()
            resultat_json = json.loads(data.get("response", "{}"))
            personnage = resultat_json.get("personnage")
            if personnage and isinstance(personnage, str) and personnage.strip():
                clean_name = personnage.strip()
                if clean_name.lower() in prompt.lower():
                    return clean_name
        return None
    except Exception as exc:
        logger.debug("Extraction d'entité ignorée: %s", exc)
        return None


def _fetch_web_backup(query: str) -> str | None:
    """Recherche des sources web complémentaires pour enrichir un contexte RAG absent ou insuffisant.
            PARAMS: - query - STR: requête de recherche
            RETURN: texte formaté des résultats web ou None si indisponible"""
    try:
        from src.features.tools.web_search import web_search
        result = web_search(query)
        if (
            result
            and "Aucun résultat trouvé sur le Web" not in result
            and "Erreur lors de la recherche Web" not in result
            and "Requête de recherche vide" not in result
        ):
            return result
    except Exception as exc:
        logger.debug("Échec du secours web_search: %s", exc)
    return None


def retrieve_rag_context(
    query: str,
    top_k: int = 5,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "qwen2.5:1.5b",
    min_sources: int = 2,
    fallback_web: bool = False,
    return_count: bool = False,
) -> str | None | tuple[str | None, int]:
    """Effectue une recherche hybride dense/sparse dans Qdrant avec repli web si les sources sont absentes ou insuffisantes.
            PARAMS: - query - STR: question ou texte recherché
                    - top_k - INT: nombre maximal de fragments documentaires à retourner (par défaut 5)
                    - qdrant_host - STR: hôte de la base vectorielle Qdrant
                    - qdrant_port - INT: port de communication Qdrant
                    - ollama_url - STR: adresse racine du serveur Ollama pour les embeddings
                    - ollama_model - STR: modèle d'extraction d'entités et d'embeddings
                    - min_sources - INT: seuil minimal de sources locales requises (par défaut 2)
                    - fallback_web - BOOL: active la recherche web de secours si sources < min_sources
                    - return_count - BOOL: retourne le tuple (contexte, nombre_de_sources_locales)
            RETURN: chaîne de contexte formatée ou tuple (contexte, nombre_sources) si return_count=True"""

    if not query or len(query.strip()) < 3:
        return (None, 0) if return_count else None
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            Fusion,
            FusionQuery,
            MatchValue,
            Prefetch,
        )
    except ImportError:
        if fallback_web:
            web_complement = _fetch_web_backup(query)
            if web_complement:
                formatted = f"[Recherche Web - Base vectorielle non installée]\n{web_complement}"
                return (formatted, 0) if return_count else formatted
        return (None, 0) if return_count else None

    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=2.0)
        if not client.collection_exists(COLLECTION_NAME):
            if fallback_web:
                web_complement = _fetch_web_backup(query)
                if web_complement:
                    formatted = f"[Recherche Web - Aucune archive locale trouvée]\n{web_complement}"
                    return (formatted, 0) if return_count else formatted
            return (None, 0) if return_count else None

        vecteur_dense = get_embedding(query)
        if not vecteur_dense:
            if fallback_web:
                web_complement = _fetch_web_backup(query)
                if web_complement:
                    formatted = f"[Recherche Web - Aucune archive locale trouvée]\n{web_complement}"
                    return (formatted, 0) if return_count else formatted
            return (None, 0) if return_count else None

        personnage_cible = extract_character(query, ollama_url=ollama_url, ollama_model=ollama_model)
        if personnage_cible:
            print(f"Personnage detecté : {personnage_cible}")
    
        qdrant_filter = None
        if personnage_cible:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="personnage_principal",
                        match=MatchValue(value=personnage_cible.lower()),
                    )
                ]
            )

        try:
            bm25 = get_bm25_model()
            sparse_vector = list(bm25.embed([query]))[0]

            reponse_qdrant = client.query_points(
                collection_name=COLLECTION_NAME,
                query_filter=qdrant_filter,
                prefetch=[
                    Prefetch(query=vecteur_dense, using="dense", limit=20),
                    Prefetch(query=sparse_vector.as_object(), using="sparse", limit=20),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
            )
        except Exception:
            reponse_qdrant = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vecteur_dense,
                query_filter=qdrant_filter,
                limit=top_k,
            )

        points = getattr(reponse_qdrant, "points", [])
        contexte_historique = ""
        source_count = 0
        for hit in points:
            source = hit.payload.get("source", "Chronique historique")
            texte = hit.payload.get("texte", "")
            if texte:
                source_count += 1
                contexte_historique += f"[Source : {source}]\n{texte}\n\n"

        contexte_historique = contexte_historique.strip()

        if fallback_web:
            if source_count == 0:
                web_complement = _fetch_web_backup(query)
                if web_complement:
                    contexte_historique = (
                        f"[Recherche Web - Aucune archive locale trouvée]\n"
                        f"{web_complement}"
                    )
            elif source_count < min_sources:
                web_complement = _fetch_web_backup(query)
                if web_complement:
                    contexte_historique = (
                        f"{contexte_historique}\n\n"
                        f"[Recherche Web - Complément pour sources locales insuffisantes ({source_count}/{min_sources})]\n"
                        f"{web_complement}"
                    )

        res_text = contexte_historique if contexte_historique else None
        if return_count:
            return res_text, source_count
        return res_text

    except Exception as exc:
        logger.debug("Échec de la récupération RAG: %s", exc)
        if fallback_web:
            web_complement = _fetch_web_backup(query)
            if web_complement:
                formatted = f"[Recherche Web - Archives locales inaccessibles]\n{web_complement}"
                return (formatted, 0) if return_count else formatted
        return (None, 0) if return_count else None
