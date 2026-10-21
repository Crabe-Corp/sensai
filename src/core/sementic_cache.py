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


def add_to_cache(client, prompt: str, llm_response: str, collection: str = "SEMENTIC_CACHE"):
    
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

def get_info_cache(client, prompt: str, collection: str = "SEMENTIC_CACHE", seuil: float = 0.85) -> str | None:
    
    response = requests.post("http://localhost:11434/api/embeddings", json={
        "model": "nomic-embed-text",
        "prompt": prompt
    })

    data = response.json()
    
    if "embedding" not in data:
        return None
        
    vecteur_dense = data["embedding"]

    try:
        resultats = client.search(
            collection_name=collection,
            query_vector=("dense", vecteur_dense),
            limit=1
        )
        
        if resultats:
            meilleur_match = resultats[0]
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

def clean_cache():
    return 0
