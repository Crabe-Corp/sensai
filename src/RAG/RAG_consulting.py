import requests
from qdrant_client import QdrantClient
# Syntaxe correcte pour importer une fonction d'un autre fichier Python
from RAG_embedding import get_embedding, COLLECTION_NAME

# Connexion à la base de données existante
client = QdrantClient("localhost", port=6333)

def get_answer(question):
    # prompt to vector
    vecteur_question = get_embedding(question)
    
    # 2. Interroger Qdrant pour trouver les 3 blocs les plus proches (Retrieval)
    reponse_qdrant = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vecteur_question,
        limit=3
    )
    
    # On extrait la liste des résultats depuis l'attribut .points
    resultats = reponse_qdrant.points
    
    # get the closest text for create the response
    contexte_historique = ""
    for hit in resultats:
        source = hit.payload["source"]
        texte = hit.payload["texte"]
        contexte_historique += f"[Source : {source}]\n{texte}\n\n"

    # create the context for the final result
    prompt_final = (
        f"Tu es un conseiller stratégique de la période des Royaumes Combattants. "
        f"Réponds à la question exclusivement en utilisant ce contexte historique :\n\n"
        f"{contexte_historique}\n\n"
        f"Question : {question}"
    )
    
    # generate the response
    print("Génération de la stratégie en cours...")
    reponse = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": prompt_final,
        "stream": False
    })
    
    print("\n=== RÉPONSE DE L'AGENT ===")
    print(reponse.json()["response"])

if __name__ == "__main__":
    prompt_utilisateur = input("Posez votre question stratégique : ")
    get_answer(prompt_utilisateur)