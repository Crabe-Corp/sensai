import os
import re
import uuid
import textwrap
import requests
import json
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams, PointStruct, SparseVectorParams
except ImportError:
    QdrantClient = None
    Distance = VectorParams = PointStruct = SparseVectorParams = None

_qdrant_client = None

def get_qdrant_client():
    """Crée le client s'il n'existe pas encore, ou retourne celui déjà existant."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = create_cache()
    return _qdrant_client

def create_cache(collection : str = "SEMENTIC_CACHE", host: str = "localhost", port=6333):
    if QdrantClient is None:
        raise ImportError("qdrant-client n'est pas installé.")
    
    client = QdrantClient(host=host, port=port)

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config={
                "dense": VectorParams(size=768, distance=Distance.COSINE)
            },
        )
    return client


def add_to_cache(prompt: str, llm_response: str, collection: str = "SEMENTIC_CACHE"):

    client = get_qdrant_client()

    response = requests.post("http://localhost:11434/api/embeddings", json={
        "model": "nomic-embed-text",
        "prompt": prompt
    })

    data = response.json()
    
    if "embedding" not in data:
        print(f"\n[!] Erreur depuis Ollama : {data.get('error', data)}")
        return False
        
    vecteur_dense = data["embedding"]

    point = PointStruct(
        id=str(uuid.uuid4()),
        vector={
            "dense": vecteur_dense
        },
        payload={
            "prompt": prompt,
            "reponse": llm_response
        }
    )

    client.upsert(
        collection_name=collection,
        points=[point]
    )
    print("Mise en cache réussie !")
    return True

def get_info_cache(prompt: str, collection: str = "SEMENTIC_CACHE", seuil: float = 0.85) -> str | None:

    client = get_qdrant_client()

    response = requests.post("http://localhost:11434/api/embeddings", json={
        "model": "nomic-embed-text",
        "prompt": prompt
    })

    data = response.json()
    
    if "embedding" not in data:
        return None
        
    vecteur_dense = data["embedding"]
        
    try:
        reponse_qdrant = client.query_points(
            collection_name=collection,
            query=vecteur_dense,
            using="dense",
            limit=1
        )
        
        points = getattr(reponse_qdrant, "points", [])
        
        if points:
            meilleur_match = points[0]
            score = meilleur_match.score
            
            print(f"[Cache] Question la plus proche : '{meilleur_match.payload.get('prompt')}' (Score: {score:.2f})")
            
            if score >= seuil:
                print("[Cache HIT] Réponse récupérée instantanément !")
                return meilleur_match.payload.get("reponse")
            else:
                print("[Cache MISS] Score trop faible. Besoin de générer la réponse.")
                return None
                
    except Exception as exc:
        print(f"[Erreur Cache] Impossible de lire Qdrant : {exc}")
        return None

    return None

def clean_cache(collection: str = "SEMENTIC_CACHE"):
    client = get_qdrant_client()
    
    if client.collection_exists(collection):
        client.delete_collection(collection_name=collection)
        print("[Cache] Base de données nettoyée avec succès.")
    
    create_cache(collection)