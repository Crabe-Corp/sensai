import os
import re
import uuid
import textwrap
import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

# Connexion à la base de données
client = QdrantClient("localhost", port=6333)
COLLECTION_NAME = "royaumes_combattants"
TAILLE_VECTEUR = 768 

if not client.collection_exists(COLLECTION_NAME):
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=TAILLE_VECTEUR, distance=Distance.COSINE),
    )

def preparer_documents_rag(dossier_source):
    documents_finaux = []
    
    for racine, _, fichiers in os.walk(dossier_source):
        for fichier in fichiers:
            if not fichier.endswith(".md"):
                continue
                
            chemin_complet = os.path.join(racine, fichier)
            nom_source = fichier.replace(".md", "").replace("_", " ").title()
            
            with open(chemin_complet, 'r', encoding='utf-8') as f:
                contenu = f.read()
                
            blocs = re.split(r'(?=\n#{2,3} )', contenu)
            
            for bloc in blocs:
                bloc_nettoye = bloc.strip()
                
                if len(bloc_nettoye) > 50:
                    # Règle de sécurité : si le bloc dépasse 2500 caractères, on le sous-découpe
                    if len(bloc_nettoye) > 2500:
                        # textwrap coupe proprement aux espaces, sans hacher les mots
                        sous_blocs = textwrap.wrap(
                            bloc_nettoye, 
                            width=2000, 
                            break_long_words=False, 
                            replace_whitespace=False
                        )
                        for i, morceau in enumerate(sous_blocs):
                            documents_finaux.append({
                                "texte": morceau,
                                # On précise la partie pour garder un historique clair
                                "source": f"{nom_source} (Partie {i+1})" 
                            })
                    else:
                        # Comportement normal pour les petits blocs
                        documents_finaux.append({
                            "texte": bloc_nettoye,
                            "source": nom_source
                        })
                    
    return documents_finaux

def get_embedding(text):
    try:
        response = requests.post("http://localhost:11434/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": text
        })
        data = response.json()
        
        # Si Ollama renvoie une erreur au lieu du vecteur
        if "embedding" not in data:
            print(f"\n[!] Error from ollama : {data.get('error', data)}")
            return None
            
        return data["embedding"]
        
    except Exception as e:
        print(f"\n[!] Erreur network Ollama : {e}")
        return None

def indexer_vers_qdrant(documents_extraits):
    points = []
    
    for index, doc in enumerate(documents_extraits):
        vecteur = get_embedding(doc["texte"])
        
        if vecteur is None:
            print(f"Bloc {index} de {doc['source']} ignoré (trop long ou erreur).")
            continue
            
        point_id = str(uuid.uuid4())
        
        points.append(
            PointStruct(
                id=point_id,
                vector=vecteur,
                payload={
                    "texte": doc["texte"],
                    "source": doc["source"]
                }
            )
        )
        print(f"Vectorisation du bloc {index} ({doc['source']})...")

    # Insertion par lots (Batching) pour respecter la limite de payload
    if points:
        TAILLE_LOT = 500
        
        # On découpe la grande liste en tranches de 500 points
        for i in range(0, len(points), TAILLE_LOT):
            lot = points[i:i + TAILLE_LOT]
            
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=lot
            )
            print(f"Lot inséré : {i} à {i + len(lot)} sur {len(points)}")
            
        print(f"\nTerminé ! {len(points)} blocs valides insérés avec succès dans Qdrant !")

if __name__ == "__main__":
    documents_prepares = preparer_documents_rag("src/RAG")
    indexer_vers_qdrant(documents_prepares)