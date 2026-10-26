import json
import logging
import os
import re
import uuid
from typing import Any

import requests
from src.core.debug import debug_print

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
    # English
    r"^(?:please\s+)?(?:can|could|would)\s+you\s+(?:please\s+)?(?:tell|explain|give|describe|provide)(?:\s+me)?(?:\s+about|\s+info|\s+information)?(?:\s+the)?\s+",
    r"^(?:tell|explain|describe)\s+me\s+about(?:\s+the)?\s+",
    r"^(?:tell|explain|describe)\s+about(?:\s+the)?\s+",
    r"^what\s+(?:do\s+you\s+know\s+about|is|are|were|was)\s+(?:the\s+)?",
    r"^who\s+(?:is|was|were)\s+(?:the\s+)?",
    r"^(?:give\s+me\s+(?:more\s+)?(?:details|info|information)\s+(?:on|about)\s+(?:the\s+)?)",
    r"^(?:s'il\s+te\s+pla[iî]t\s*,?\s*)?(?:peux|pourrais|pourriez)-tu(?:\s+s'il\s+te\s+pla[iî]t)?\s+(?:me\s+)?(?:parler|dire|expliquer|donner)(?:\s+de|\s+des|\s+du|\s+d'|\s+sur)?(?:\s+le|\s+la|\s+les|\s+l')?\s+",
    r"^(?:parle|dis|explique)-moi(?:\s+de|\s+des|\s+du|\s+d'|\s+sur)?(?:\s+le|\s+la|\s+les|\s+l')?\s+",
    r"^qu'est(?:-|\s+)ce\s+que\s+(?:c'est\s+que\s+|les?\s+|la\s+|l')?",
    r"^qui\s+(?:est|était|étaient|fut|furent)\s+(?:les?\s+|la\s+|l')?",
    r"^donne-moi\s+(?:des\s+informations|des\s+infos|des\s+détails)\s+(?:sur|concernant)\s+",
]


def normalize_prompt(prompt: str) -> str:
    """Normalize a prompt by stripping conversational filler words and punctuation.
            PARAMS: - prompt - STR: raw user query text
            RETURN: clean normalized string for semantic comparison"""
    if not prompt:
        return ""
    text = prompt.strip().lower()
    text = re.sub(r"[?!.,;:\"']+$", "", text).strip()
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(?:the|a|an|le|la|les|l'|un|une|des|du)\s+", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normaliser_prompt(prompt: str) -> str:
    return normalize_prompt(prompt)


def lexical_similarity(prompt1: str, prompt2: str) -> float:
    """Compute the Jaccard similarity coefficient on significant stems of two prompts.
            PARAMS: - prompt1 - STR: first prompt
                    - prompt2 - STR: second prompt
            RETURN: similarity float score between 0.0 and 1.0"""
    norm1 = normalize_prompt(prompt1)
    norm2 = normalize_prompt(prompt2)
    words1 = {m for m in re.findall(r"\b\w{2,}\b", norm1) if m not in STOP_WORDS}
    words2 = {m for m in re.findall(r"\b\w{2,}\b", norm2) if m not in STOP_WORDS}
    if not words1 or not words2:
        return 0.0
    stems1 = {m[:4] for m in words1}
    stems2 = {m[:4] for m in words2}
    intersection = stems1 & stems2
    union = stems1 | stems2
    return len(intersection) / len(union) if union else 0.0


def similarite_lexicale(prompt1: str, prompt2: str) -> float:
    return lexical_similarity(prompt1, prompt2)


def verify_intent_equivalence(
    prompt_cache: str,
    prompt_nouveau: str,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen2.5:1.5b",
) -> bool:
    """Verify via a lightweight LLM call if two queries share identical intent.
            PARAMS: - prompt_cache - STR: question already present in cache
                    - prompt_nouveau - STR: new user question
                    - ollama_url - STR: Ollama server base URL
                    - model - STR: model name for JSON verification
            RETURN: boolean True if intent is equivalent, False otherwise"""
    system_prompt = (
        "You are a semantic validator for a question-answering cache.\n"
        "Determine if Question B has the same intent and seeks the same information as Question A, "
        "such that the answer to Question A perfectly answers Question B.\n"
        "Consider obvious rephrasings, synonyms and typos equivalent "
        "(e.g. '7 warrior states' and '7 warring states' refer to the exact same 7 Warring States).\n"
        "If subjects, kingdoms or figures differ (e.g. Qin vs Zhao, Li Xin vs Han Xin), answer false.\n"
        "Reply STRICTLY in JSON: {\"same_intent\": true} or {\"same_intent\": false}."
    )
    user_prompt = f"Question A (cached): \"{prompt_cache}\"\nQuestion B (new): \"{prompt_nouveau}\""

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
            return bool(res_json.get("same_intent", res_json.get("meme_intention", False)))
    except Exception as exc:
        logger.debug("[LLM intent verification skipped] %s", exc)

    return False


def verifier_equivalence_intention(
    prompt_cache: str,
    prompt_nouveau: str,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen2.5:1.5b",
) -> bool:
    return verify_intent_equivalence(prompt_cache, prompt_nouveau, ollama_url, model)


def get_dense_embedding(prompt: str, ollama_url: str = "http://localhost:11434") -> list[float] | None:
    """Generate dense embedding vector via nomic-embed-text with task prefix 'search_query:'.
            PARAMS: - prompt - STR: query text to vectorize
                    - ollama_url - STR: Ollama server base URL
            RETURN: list of 768 floats or None on failure"""
    cleaned = normalize_prompt(prompt)
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
        logger.debug("[Embedding cache error] %s", exc)
        return None


def get_qdrant_client(host: str = "localhost", port: int = 6333):
    """Retrieve active Qdrant client instance or initialize if needed.
            PARAMS: - host - STR: Qdrant host
                    - port - INT: Qdrant port
            RETURN: active QdrantClient instance"""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = create_cache(host=host, port=port)
    return _qdrant_client


def create_cache(collection: str = "SEMENTIC_CACHE", host: str = "localhost", port: int = 6333):
    """Initialize Qdrant collection for semantic cache if needed.
            PARAMS: - collection - STR: collection name
                    - host - STR: Qdrant host address
                    - port - INT: Qdrant port
            RETURN: active QdrantClient instance"""
    if QdrantClient is None:
        raise ImportError("qdrant-client is not installed.")

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
    """Add a question-answer pair to the vector semantic cache.
            PARAMS: - prompt - STR: user query
                    - llm_response - STR: response generated by LLM
                    - collection - STR: Qdrant collection name
                    - ollama_url - STR: Ollama server base URL
            RETURN: bool True on success, False otherwise"""
    client = get_qdrant_client()
    vector = get_dense_embedding(prompt, ollama_url=ollama_url)
    if not vector:
        return False

    prompt_norm = normalize_prompt(prompt)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector={"dense": vector},
        payload={
            "prompt": prompt,
            "prompt_norm": prompt_norm,
            "reponse": llm_response,
        },
    )
    client.upsert(collection_name=collection, points=[point])
    debug_print("[Cache] Entry cached successfully.")
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
    """Query semantic cache with multi-tier matching and intent confirmation.
            PARAMS: - prompt - STR: query to search
                    - collection - STR: Qdrant collection name
                    - seuil - FLOAT | NONE: legacy threshold for backward compatibility
                    - seuil_haut - FLOAT: cosine similarity threshold for immediate validation (0.80)
                    - seuil_bas - FLOAT: minimum threshold to enter intent verification (0.65)
                    - ollama_url - STR: Ollama server base URL
                    - model - STR: model name for intent validation
            RETURN: cached response if HIT, None if MISS"""
    if seuil is not None:
        seuil_haut = seuil

    client = get_qdrant_client()
    vector = get_dense_embedding(prompt, ollama_url=ollama_url)
    if not vector:
        return None

    prompt_norm = normaliser_prompt(prompt)

    try:
        qdrant_resp = client.query_points(
            collection_name=collection,
            query=vector,
            using="dense",
            limit=3,
        )
        points = getattr(qdrant_resp, "points", [])
        if not points:
            return None

        for match in points:
            cached_prompt = match.payload.get("prompt", "")
            cached_norm = match.payload.get("prompt_norm") or normaliser_prompt(cached_prompt)
            score = match.score

            # Tier 1: Exact match after normalization
            if prompt_norm and cached_norm and prompt_norm == cached_norm:
                debug_print(f"[Cache HIT Exact] Match found: '{cached_prompt}' (Score: 1.00)")
                return match.payload.get("reponse")

            debug_print(f"[Cache] Nearest question: '{cached_prompt}' (Score: {score:.2f})")

            # Tier 2: Strong cosine similarity (>= seuil_haut)
            if score >= seuil_haut:
                debug_print(f"[Cache HIT Direct] Retrieved response instantly! (Score: {score:.2f} >= {seuil_haut:.2f})")
                return match.payload.get("reponse")

            # Tier 3: Verification zone (seuil_bas <= score < seuil_haut)
            if score >= seuil_bas:
                same_intent = verifier_equivalence_intention(
                    prompt_cache=cached_prompt,
                    prompt_nouveau=prompt,
                    ollama_url=ollama_url,
                    model=model,
                )
                if same_intent:
                    debug_print(f"[Cache HIT Confirmed] Semantic intent validated for: '{cached_prompt}' (Score: {score:.2f})")
                    return match.payload.get("reponse")

                sim_lex = similarite_lexicale(cached_prompt, prompt)
                if sim_lex >= 0.50:
                    debug_print(f"[Cache HIT Lexical] Keywords aligned ({sim_lex:.0%}) for: '{cached_prompt}' (Score: {score:.2f})")
                    return match.payload.get("reponse")

                debug_print(f"[Cache MISS] Question close '{cached_prompt}' but intent differs or unconfirmed.")
                return None

        debug_print(f"[Cache MISS] Score too low ({points[0].score:.2f} < {seuil_bas:.2f}). Generating response.")
        return None

    except Exception as exc:
        debug_print(f"[Cache Error] Failed to read from Qdrant: {exc}")
        return None


def clean_cache(collection: str = "SEMENTIC_CACHE"):
    """Clean the semantic cache collection.
            PARAMS: - collection - STR: collection name to reset
            RETURN: None"""
    client = get_qdrant_client()
    if client.collection_exists(collection):
        client.delete_collection(collection_name=collection)
        debug_print("[Cache] Database cleaned successfully.")
    create_cache(collection)
