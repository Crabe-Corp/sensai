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


def retrieve_rag_context(query: str, top_k: int = 5, qdrant_host: str = "localhost", qdrant_port: int = 6333, ollama_url: str = "http://localhost:11434", ollama_model: str = "qwen2.5:1.5b") -> str | None:
    """Effectue une recherche hybride dense/sparse dans Qdrant pour enrichir le contexte historique.
            PARAMS: - query - STR: question ou texte recherché
                    - top_k - INT: nombre maximal de fragments documentaires à retourner
                    - qdrant_host - STR: hôte de la base vectorielle Qdrant
                    - qdrant_port - INT: port de communication Qdrant
                    - ollama_url - STR: adresse racine du serveur Ollama pour les embeddings
            RETURN: chaîne de contexte historique formatée ou None si aucun résultat"""

    if not query or len(query.strip()) < 3:
        return None
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
        return None

    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=2.0)
        if not client.collection_exists(COLLECTION_NAME):
            return None

        vecteur_dense = get_embedding(query)
        if not vecteur_dense:
            return None

        personnage_cible = extract_character(query, ollama_url=ollama_url, ollama_model=ollama_model)
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
                using="dense",
                query_filter=qdrant_filter,
                limit=top_k,
            )

        points = getattr(reponse_qdrant, "points", [])

        if not points and qdrant_filter is not None:
            print(f"[RAG] Filtre strict bloquant. Recherche globale pour le texte...")
            try:
                reponse_qdrant = client.query_points(
                    collection_name=COLLECTION_NAME,
                    query_filter=None, # ON ENLÈVE LE FILTRE
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
                    using="dense",
                    query_filter=None,
                    limit=top_k,
                )
            points = getattr(reponse_qdrant, "points", [])


        if not points:
            return None

        contexte_historique = ""
        for hit in points:
            source = hit.payload.get("source", "Chronique historique")
            texte = hit.payload.get("texte", "")
            if texte:
                contexte_historique += f"[Source : {source}]\n{texte}\n\n"

        return contexte_historique.strip() if contexte_historique.strip() else None

    except Exception as exc:
        logger.debug("Échec de la récupération RAG: %s", exc)
        return None