---
title: "Système d'Outils & MCP"
description: "Création d'outils avec @tool, registre dynamique et serveurs MCP."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/fr/tools-guide.md"
sidebar:
  order: 1
---
SensAI intègre une architecture modulaire permettant d'étendre facilement les capacités de l'agent avec des outils Python natifs ou des serveurs distants via le protocole standard **Model Context Protocol (MCP)** d'Anthropic.

---

## Créer un Outil Natif avec le décorateur `@tool`

Tous les outils natifs de SensAI résident dans le module `src/features/tools/`. Pour créer un nouvel outil :

### 1. Déclaration de la fonction

Utilisez le décorateur `@tool` importé depuis `src.features.tools.registry`. Le décorateur analyse automatiquement les annotations de type Python et la docstring pour générer le schéma JSON Schema transmis à Ollama :

```python
# src/features/tools/mon_nouvel_outil.py
from typing import Any, Dict
from src.features.tools.registry import tool

@tool
def evaluer_moral_armee(royaume: str, solde_retard: int = 0) -> Dict[str, Any]:
    """Évalue l'état de combativité et le moral d'une armée en fonction de ses conditions.
    
    PARAMS:
        - royaume - STR: Nom du royaume concerné (ex: Qin, Chu, Zhao)
        - solde_retard - INT: Nombre de mois de retard de versement des soldes
        
    RETURN:
        - Dictionnaire contenant le score de moral et les risques de désertion
    """
    if solde_retard > 3:
        return {
            "royaume": royaume,
            "moral": "critique",
            "score": 25,
            "risque_desertion": "très élevé",
            "conseil": "Payer immédiatement les soldes ou subir une mutinerie."
        }
    
    return {
        "royaume": royaume,
        "moral": "bon",
        "score": 85,
        "risque_desertion": "faible",
        "conseil": "L'armée est prête pour la campagne militaire."
    }
```

### 2. Enregistrement dans le registre par défaut

Dans `src/features/tools/__init__.py` ou `builtin.py`, assurez-vous que le fichier est importé pour que le décorateur s'enregistre dans `default_registry` :

```python
from . import mon_nouvel_outil  # Enregistre automatiquement l'outil
```

### 3. Exposition Côté Web (Backend)

Dans `backend/tools_registry.py` :
1. Associez une icône Lucide et une catégorie dans `_TOOL_UI` :
   ```python
   _TOOL_UI["evaluer_moral_armee"] = ("ShieldAlert", "Militaire")
   ```
2. Si l'outil est une action destructive (écriture de données ou suppression), ajoutez son nom au set `DESTRUCTIVE_TOOLS` :
   ```python
   DESTRUCTIVE_TOOLS.add("mon_outil_destructif")
   ```
3. Si l'outil est un outil de lecture interne que l'IA doit toujours avoir sous la main (comme le RAG), ajoutez-le à `READ_ONLY_TOOLS` :
   ```python
   READ_ONLY_TOOLS.add("evaluer_moral_armee")
   ```

---

## Intégration d'un Serveur MCP Externe

SensAI implémente le client standard **Model Context Protocol (MCP)** (`src/features/tools/mcp_client.py`) pour communiquer avec des serveurs MCP sur l'entrée/sortie standard (`stdio`).

### Structure d'un Serveur MCP Démo

Un exemple complet est fourni dans `src/features/tools/mcp_server_demo.py` :

```python
# Extrait du serveur MCP
import json
import sys

# Métadonnées exposées via tools/list
TOOLS_METADATA = [
    {
        "name": "calculate_grain_supply",
        "description": "Calcule la quantité de grain nécessaire pour une armée.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kingdom": {"type": "string"},
                "soldiers": {"type": "integer"},
                "months": {"type": "integer", "default": 3}
            },
            "required": ["kingdom", "soldiers"]
        }
    }
]

def handle_request(req):
    method = req.get("method")
    if method == "tools/list":
        return {"tools": TOOLS_METADATA}
    elif method == "tools/call":
        params = req.get("params", {})
        # Exécution de la fonction correspondante
        return {"content": [{"type": "text", "text": "..."}]}
```

### Connexion Dynamique via l'API Web

SensAI propose une route dédiée pour attacher un serveur MCP à chaud sans redémarrer le backend :

```bash
curl -X POST http://localhost:8080/api/mcp/connect \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python",
    "args": ["-m", "src.features.tools.mcp_server_demo"],
    "prefix": "mcp_"
  }'
```

Le backend instancie le client MCP, négocie le protocole `initialize`, découvre les outils avec `tools/list` et les ajoute immédiatement au `ToolRegistry`. Ils apparaissent automatiquement dans le sélecteur d'outils du frontend !

---

## Bonnes Pratiques de Sécurité pour les Outils

1. **Jamais d'exécution SQL brute :** Utiliser des requêtes paramétrées avec SQLite pour éviter les injections SQL (`sqlite3` / SQLAlchemy).
2. **Confinement de fichiers (Path Traversal) :** Valider systématiquement que les chemins de fichiers restent contenus dans les répertoires autorisés (`manuscrit_royaumes/`, `exports/`).
3. **Validation des types :** Déclarer des types précis (`int`, `str`, `float`, `list[str]`) afin qu'Ollama respecte scrupuleusement les contraintes de typage lors des appels de fonction.
