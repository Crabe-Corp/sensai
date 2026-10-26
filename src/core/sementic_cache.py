import json
import logging
import os
import re
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, PointStruct, VectorParams
except ImportError:
    QdrantClient = None
    Distance = VectorParams = PointStruct = None

_qdrant_client = None

STOP_WORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
    "le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "et", "ou", "en", "dans", "sur", "par", "pour", "avec",
}

FILLER_PATTERNS = [
    r"^(?:please\s+)?(?:can|could|would)\s+you\s+(?:please\s+)?(?:tell|explain|give|describe|provide)(?:\s+me)?(?:\s+about|\s+info|\s+information)?(?:\s+the)?\s+",
    r"^(?:tell|explain|describe)\s+me\s+about(?:\s+the)?\s+",
    r"^(?:tell|explain|describe)\s+about(?:\s+the)?\s+",
    r"^what\s+(?:do\s+you\s+know\s+about|is|are|were|was)\s+(?:the\s+)?",
    r"^who\s+(?:is|was|were)\s+(?:the\s+)?",
    r"^(?:give\s+me\s+(?:more\s+)?(?:details|info|information)\s+(?:on|about)\s+(?:the\s+)?)"
]


def normaliser_prompt(prompt: str) -> str:
    """Normalise une requête en retirant la ponctuation parasite et les formules de politesse conversationnelles.
            PARAMS: - prompt - STR: texte brut de la requête utilisateur
            RETURN: chaîne normalisée et nettoyée pour comparaison sémantique"""
    if not prompt:
        return ""
    texte = prompt.strip().lower()
    texte = re.sub(r"[?!.,;:\"']+$", "", texte).strip()
    for pattern in FILLER_PATTERNS:
        texte = re.sub(pattern, "", texte, flags=re.IGNORECASE).strip()
    texte = re.sub(r"^(?:the|a|an|le|la|les|l'|un|une|des|du)\s+", "", texte).strip()
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte


def similarite_lexicale(prompt1: str, prompt2: str) -> float:
    """Calcule le coefficient de Jaccard sur les racines/mots significatifs de deux requêtes.
            PARAMS: - prompt1 - STR: première requête
                    - prompt2 - STR: deuxième requête
            RETURN: score flottant de similarité entre 0.0 et 1.0"""
    norm1 = normaliser_prompt(prompt1)
    norm2 = normaliser_prompt(prompt2)
    mots1 = {m for m in re.findall(r"\b\w{2,}\b", norm1) if m not in STOP_WORDS}
    mots2 = {m for m in re.findall(r"\b\w{2,}\b", norm2) if m not in STOP_WORDS}
    if not mots1 or not mots2:
        return 0.0
    racines1 = {m[:4] for m in mots1}
    racines2 = {m[:4] for m in mots2}
    intersection = racines1 & racines2
    union = racines1 | racines2
    return len(intersection) / len(union) if union else 0.0


def verifier_equivalence_intention(
    prompt_cache: str,
    prompt_nouveau: str,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen2.5:1.5b",
) -> bool:
    """Vérifie via un appel LLM ultra-rapide si deux requêtes partagent la même intention exacte.
            PARAMS: - prompt_cache - STR: question déjà présente dans le cache
                    - prompt_nouveau - STR: nouvelle question posée par l'utilisateur
                    - ollama_url - STR: adresse racine du serveur Ollama
                    - model - STR: nom du modèle pour la vérification JSON
            RETURN: booléen True si l'intention est équivalente, False sinon"""
    system_prompt = (
        "Tu es un vérificateur sémantique pour un cache de questions-réponses.\n"
        "Détermine si la Question B a la même intention et demande la même information que la Question A, "
        "de sorte que la réponse à la Question A réponde parfaitement à la Question B.\n"
        "Considère comme équivalentes les reformulations et synonymes évidents "
        "(ex: '7 warrior states' et '7 warring states' désignent les mêmes 7 Royaumes Combattants).\n"
        "Si les sujets, souverains ou personnages diffèrent (ex: Qin vs Zhao, Li Xin vs Han Xin), réponds faux.\n"
        "Réponds UNIQUEMENT au format JSON strict : {\"meme_intention\": true} ou {\"meme_intention\": false}."
    )
    user_prompt = f"Question A (en cache) : \"{prompt_cache}\"\nQuestion B (nouvelle) : \"{prompt_nouveau}\""

    try:
        response = requests.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False,
                "format": "json",
            },
            timeout=3.0,
        )
        if response.status_code == 200:
            data = response.json()
            res_json = json.loads(data.get("response", "{}"))
            return bool(res_json.get("meme_intention", False))
    except Exception as exc:
        logger.debug("[Vérification intention LLM ignorée] %s", exc)

    return False


def get_dense_embedding(prompt: str, ollama_url: str = "http://localhost:11434") -> list[float] | None:
    """Génère le vecteur d'embedding dense via nomic-embed-text avec préfixe de tâche 'search_query:'.
            PARAMS: - prompt - STR: texte de la requête à vectoriser
                    - ollama_url - STR: adresse racine du serveur Ollama
            RETURN: liste de flottants de taille 768 ou None en cas d'échec"""
    cleaned = normaliser_prompt(prompt)
    task_prompt = f"search_query: {cleaned}" if cleaned else prompt

    try:
        response = requests.post(
            f"{ollama_url.rstrip('/')}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": task_prompt},
            timeout=10.0,
        )
        data = response.json()
        if "embedding" not in data:
            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": prompt},
                timeout=10.0,
            )
            data = response.json()
        return data.get("embedding")
    except Exception as exc:
        logger.debug("[Erreur embedding cache] %s", exc)
        return None


def get_qdrant_client(host: str = "localhost", port: int = 6333):
    """Crée le client Qdrant s'il n'existe pas encore, ou retourne celui déjà existant.
            PARAMS: - host - STR: hôte Qdrant
                    - port - INT: port Qdrant
            RETURN: instance active du client QdrantClient"""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = create_cache(host=host, port=port)
    return _qdrant_client


def create_cache(collection: str = "SEMENTIC_CACHE", host: str = "localhost", port: int = 6333):
    """Initialise la collection Qdrant dédiée au cache sémantique si nécessaire.
            PARAMS: - collection - STR: nom de la collection
                    - host - STR: adresse d'hôte du serveur Qdrant
                    - port - INT: port du serveur Qdrant
            RETURN: instance active de QdrantClient"""
    if QdrantClient is None:
        raise ImportError("qdrant-client n'est pas installé.")

    client = QdrantClient(host=host, port=port)

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
        )
    return client


def add_to_cache(
    prompt: str,
    llm_response: str,
    collection: str = "SEMENTIC_CACHE",
    ollama_url: str = "http://localhost:11434",
) -> bool:
    """Ajoute une paire question-réponse dans le cache sémantique vectoriel.
            PARAMS: - prompt - STR: question posée par l'utilisateur
                    - llm_response - STR: réponse générée par le modèle
                    - collection - STR: nom de la collection Qdrant
                    - ollama_url - STR: adresse racine du serveur Ollama
            RETURN: booléen True en cas de succès, False sinon"""
    client = get_qdrant_client()
    vecteur = get_dense_embedding(prompt, ollama_url=ollama_url)
    if not vecteur:
        return False

    prompt_norm = normaliser_prompt(prompt)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector={"dense": vecteur},
        payload={
            "prompt": prompt,
            "prompt_norm": prompt_norm,
            "reponse": llm_response,
        },
    )
    client.upsert(collection_name=collection, points=[point])
    print("Mise en cache réussie !")
    return True


def get_info_cache(
    prompt: str,
    collection: str = "SEMENTIC_CACHE",
    seuil: float | None = None,
    seuil_haut: float = 0.80,
    seuil_bas: float = 0.65,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen2.5:1.5b",
) -> str | None:
    """Interroge le cache sémantique avec matching multi-niveaux et vérification d'intention.
            PARAMS: - prompt - STR: question courante à rechercher
                    - collection - STR: nom de la collection Qdrant
                    - seuil - FLOAT | NONE: seuil historique pour rétrocompatibilité
                    - seuil_haut - FLOAT: seuil de similarité cosinus pour validation immédiate (0.80)
                    - seuil_bas - FLOAT: seuil minimal pour entrer en zone de vérification (0.65)
                    - ollama_url - STR: adresse racine du serveur Ollama
                    - model - STR: nom du modèle pour la validation d'intention
            RETURN: réponse en cache si HIT, ou None si MISS"""
    if seuil is not None:
        seuil_haut = seuil

    client = get_qdrant_client()
    vecteur = get_dense_embedding(prompt, ollama_url=ollama_url)
    if not vecteur:
        return None

    prompt_norm = normaliser_prompt(prompt)

    try:
        reponse_qdrant = client.query_points(
            collection_name=collection,
            query=vecteur,
            using="dense",
            limit=3,
        )
        points = getattr(reponse_qdrant, "points", [])
        if not points:
            return None

        for match in points:
            cached_prompt = match.payload.get("prompt", "")
            cached_norm = match.payload.get("prompt_norm") or normaliser_prompt(cached_prompt)
            score = match.score

            # Niveau 1 : Correspondance exacte après normalisation
            if prompt_norm and cached_norm and prompt_norm == cached_norm:
                print(f"[Cache HIT Exact] Correspondance trouvée : '{cached_prompt}' (Score: 1.00)")
                return match.payload.get("reponse")

            print(f"[Cache] Question la plus proche : '{cached_prompt}' (Score: {score:.2f})")

            # Niveau 2 : Similarité cosinus forte (>= seuil_haut)
            if score >= seuil_haut:
                print(f"[Cache HIT Direct] Réponse récupérée instantanément ! (Score: {score:.2f} >= {seuil_haut:.2f})")
                return match.payload.get("reponse")

            # Niveau 3 : Zone de vérification (seuil_bas <= score < seuil_haut)
            if score >= seuil_bas:
                # 1. Vérification d'intention par LLM
                meme_intention = verifier_equivalence_intention(
                    prompt_cache=cached_prompt,
                    prompt_nouveau=prompt,
                    ollama_url=ollama_url,
                    model=model,
                )
                if meme_intention:
                    print(f"[Cache HIT Confirmé] Intention sémantique validée pour '{cached_prompt}' (Score: {score:.2f})")
                    return match.payload.get("reponse")

                # 2. Repli sur l'overlap lexical si le LLM n'a pas répondu
                sim_lex = similarite_lexicale(cached_prompt, prompt)
                if sim_lex >= 0.50:
                    print(f"[Cache HIT Lexical] Mots-clés alignés ({sim_lex:.0%}) pour '{cached_prompt}' (Score: {score:.2f})")
                    return match.payload.get("reponse")

                print(f"[Cache MISS] Question proche '{cached_prompt}' mais intention différente ou non confirmée.")
                return None

        print(f"[Cache MISS] Score trop faible ({points[0].score:.2f} < {seuil_bas:.2f}). Besoin de générer la réponse.")
        return None

    except Exception as exc:
        print(f"[Erreur Cache] Impossible de lire Qdrant : {exc}")
        return None


def clean_cache(collection: str = "SEMENTIC_CACHE"):
    """Nettoie intégralement la collection de cache sémantique.
            PARAMS: - collection - STR: nom de la collection à réinitialiser
            RETURN: None"""
    client = get_qdrant_client()
    if client.collection_exists(collection):
        client.delete_collection(collection_name=collection)
        print("[Cache] Base de données nettoyée avec succès.")
    create_cache(collection)
