from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText, MatchValue

# Pensez à mettre le vrai nom de votre collection !
COLLECTION_NAME = "royaumes_combattants"

client = QdrantClient(host="localhost", port=6333)

print("🔍 Recherche de 'Li Xin' dans les métadonnées de Qdrant...\n")

# On utilise scroll() pour fouiller toute la base sans utiliser les vecteurs
records, next_page = client.scroll(
    collection_name=COLLECTION_NAME,
    # On filtre pour trouver n'importe quel payload qui contient ce nom
    # (MatchText est un peu plus tolérant que MatchValue)
    limit=10,
    with_payload=True,
    with_vectors=False
)

trouve = False
for record in records:
    payload = record.payload
    
    # On vérifie dans tout le payload si "Li Xin" apparaît
    payload_str = str(payload).lower()
    if "li xin" in payload_str:
        trouve = True
        print(f"✅ TROUVÉ DANS LE POINT ID : {record.id}")
        
        # On affiche spécifiquement la clé personnage_principal si elle existe
        if "personnage_principal" in payload:
            valeur = payload["personnage_principal"]
            print(f"👉 Valeur exacte de la clé 'personnage_principal' : '{valeur}'")
        else:
            print("❌ La clé 'personnage_principal' n'existe pas pour ce point, le nom est ailleurs !")
            
        print(f"Aperçu du texte : {payload.get('texte', '')[:100]}...\n")

if not trouve:
    print("❌ 'Li Xin' est introuvable dans le payload des premiers documents de la collection.")