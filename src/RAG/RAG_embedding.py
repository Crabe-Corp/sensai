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

COLLECTION_NAME = "royaumes_combattants"
TAILLE_VECTEUR = 768
_bm25_model = None


def get_bm25_model():
    """Charge le modèle BM25 à la demande pour éviter un coût réseau au chargement du module.
            PARAMS: Aucun
            RETURN: instance du modèle SparseTextEmbedding"""

    global _bm25_model
    if _bm25_model is None:
        from fastembed import SparseTextEmbedding
        _bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _bm25_model


class _BM25Proxy:
    def embed(self, *args, **kwargs):
        """Délègue l'encodage sparse au modèle BM25 instancié paresseusement.
                PARAMS: - args, kwargs - ANY: arguments transmis à SparseTextEmbedding.embed
                RETURN: itérateur ou liste de représentations de vecteurs sparse"""

        return get_bm25_model().embed(*args, **kwargs)


bm25_model = _BM25Proxy()


def get_qdrant_client(host: str = "localhost", port: int = 6333):
    """Initialise le client Qdrant et s'assure que la collection existe.
            PARAMS: - host - STR: adresse d'hôte du serveur Qdrant
                    - port - INT: port d'écoute du serveur Qdrant
            RETURN: instance active du client QdrantClient"""

    if QdrantClient is None:
        raise ImportError("qdrant-client n'est pas installé.")
    client = QdrantClient(host=host, port=port)

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(size=TAILLE_VECTEUR, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams()
            }
        )
    return client

def preparer_documents_rag(dossier_source):
    """Découpe et prépare les fichiers markdown des chroniques en segments indexables.
            PARAMS: - dossier_source - STR: chemin vers le dossier contenant les fichiers markdown
            RETURN: liste de dictionnaires contenant le texte et la source de chaque segment"""

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
    """Génère l'embedding dense d'un texte via l'API d'embeddings Ollama.
            PARAMS: - text - STR: texte source à vectoriser
            RETURN: liste de flottants représentant le vecteur dense ou None en cas d'erreur"""

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

def get_metadata(text):
    """Extrait le personnage historique principal du texte via un appel LLM Ollama.
            PARAMS: - text - STR: extrait textuel à analyser
            RETURN: dictionnaire contenant les métadonnées extraites"""

    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "qwen2.5:3b",
            # possibilité de modifier ce filtre pour ajouter des precision si par exemple on veut aussi le pays
            "prompt": f"Extraire le personnage historique principal de ce texte. Retourne UNIQUEMENT un format JSON valide strict, par exemple: {{\"personnage_principal\": \"Li Xin\"}}. S'il n'y en a pas, retourne {{\"personnage_principal\": \"Aucun\"}}. Texte : {text}",
            "stream": False,
            "format": "json"
        })
        data = response.json()

        if "response" not in data:
            print(f"\n[!] Erreur from ollama : {data.get('error', data)}")
            return {}
            
        return json.loads(data["response"])
        
    except Exception as e:
        print(f"\n[!] Erreur d'extraction de métadonnées : {e}")
        return {}

def indexer_vers_qdrant(documents_extraits):
    """Génère les embeddings denses et sparses puis insère les documents par lots dans Qdrant.
            PARAMS: - documents_extraits - LIST: liste de dictionnaires de documents avec texte et source
            RETURN: None"""

    client = get_qdrant_client()
    points = []
    
    for index, doc in enumerate(documents_extraits):
        vecteur = get_embedding(doc["texte"])
        metadata_ia = get_metadata(doc["texte"])
    
        personnage_extrait = metadata_ia.get("personnage_principal")

        if personnage_extrait and personnage_extrait != "Aucun":
            if personnage_extrait.lower() not in doc["texte"].lower():
                print(f"[!] Hallucination détectée : l'IA a inventé '{personnage_extrait}'. Ignoré.")
                metadata_ia["personnage_principal"] = "Aucun"
        
        if vecteur is None:
            print(f"Bloc {index} de {doc['source']} ignoré (trop long ou erreur).")
            continue

        vecteur_sparse = list(bm25_model.embed([doc["texte"]]))[0]

        point_id = str(uuid.uuid4())
        
        # Fusion du texte, de la source, et des métadonnées générées
        payload_complet = {
            "texte": doc["texte"],
            "source": doc["source"],
            **metadata_ia
        }

        points.append(
            PointStruct(
                id=point_id,
                vector={
                    "dense": vecteur,
                    "sparse": vecteur_sparse.as_object()
                },
                payload=payload_complet
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