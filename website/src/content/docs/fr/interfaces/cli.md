---
title: "Guide du CLI SensAI"
description: "Commandes, options, modes /encyclopedia et /simulation."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/fr/cli.md"
sidebar:
  order: 1
---
Le terminal en ligne de commande (CLI) est le cœur historique et le moteur d'exécution de référence de SensAI. Il offre une interaction directe en streaming avec les modèles locaux Ollama, un enrichissement documentaire pré-génération via le RAG vectoriel, ainsi qu'un simulateur de conflit tactique complet.

---

## Lancement et Options

Pour démarrer la CLI, exécutez le module principal depuis la racine du dépôt :

```bash
python -m src.interfaces.cli.main [OPTIONS]
```

### Paramètres de la ligne de commande

| Option | Raccourci | Type | Valeur par défaut | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--model` | `-m` | `str` | `llama3` | Nom du modèle Ollama à utiliser (recommandé : `qwen2.5:7b`). |
| `--host` | | `str` | `http://localhost:11434` | URL racine du serveur Ollama local ou distant. |
| `--max-tokens` | `-t` | `int` | `32768` | Budget de contexte maximal alloué à la session. |
| `--tools` | | `bool` | `False` | Active le chargement des outils locaux et du serveur MCP de démo. |
| `--profile` | `-p` | `str` | `None` | Charge un profil d'historique utilisateur spécifique. |
| `--rag` | | `bool` | `True` | Active la recherche documentaire automatique dans Qdrant. |
| `--debug` | | `bool` | `False` | Affiche les logs internes, les scores de similarité et le RAG. |

---

## Modes de Fonctionnement

Le CLI propose deux modes fondamentaux accessibles par commandes slash :

<pre class="mermaid">
stateDiagram-v2
    [*] --&gt; Encyclopedia : Lancement par défaut
    Encyclopedia --&gt; Simulation : /simulation [seed]
    Simulation --&gt; Encyclopedia : /encyclopedia
    Encyclopedia --&gt; [*] : /exit
    Simulation --&gt; [*] : /exit
</pre>

### 1. Le Mode Encyclopédie (`/encyclopedia`) — Mode par défaut

En mode Encyclopédie, l'agent incarne un **grand conseiller impérial et érudit des Sept Royaumes Combattants**.

- **Enrichissement RAG Automatique :** Chaque question posée fait l'objet d'une recherche vectorielle hybride préalable dans la base Qdrant (`retriever.py`). Les extraits d'archives authentiques (*Shiji*, *Zhan Guo Ce*) sont injectés directement dans le contexte du modèle avant la génération.
- **Règles Historiques Intégrées :**
  - **Correction des effectifs militaires (Wan x10) :** Les textes anciens traduisent souvent l'unité chinoise "Wan" (10 000) de manière littérale (ex: 20 000). Le modèle réajuste automatiquement les effectifs à l'échelle historique réelle (ex: 200 000 soldats).
  - **Désambiguïsation des généraux :** Empêche les amalgames entre figures portant des patronymes proches (ex: Li Xin vs Han Xin vs Wang Jian).
  - **Repli Web gracieux :** Si aucune chronique locale ne couvre le sujet, le CLI effectue une recherche web complémentaire (*DuckDuckGo* / *Wikipedia*) sans halluciner.

### 2. Le Mode Simulation (`/simulation [seed]`)

Le mode simulation transforme l'agent en **Maître de Guerre (*War Master*)** d'un wargame au tour par tour entre les 7 royaumes (Qin, Chu, Qi, Zhao, Wei, Han, Yan).

- **Chat libre désactivé (`free_chat: False`) :** L'agent n'a le droit d'affirmer aucun chiffre, aucun résultat et aucun mouvement qui ne provienne directement d'un appel d'outil vérifié (`simulate_battle`, `get_kingdom_state`, `list_kingdoms`).
- **Graine aléatoire reproductible (`seed`) :** Permet de rejouer des campagnes tactiques avec le même état initial.
- **Rapport de bataille structuré :** L'agent analyse les pertes, les gains territoriaux et le ravitaillement à partir des données chiffrées strictes.

---

## Commandes Disponibles en Session

| Commande | Description |
| :--- | :--- |
| `/help` | Affiche l'ensemble des commandes et options disponibles. |
| `/simulation [seed]` | Bascule en mode simulation de conflit avec un état de jeu frais. |
| `/encyclopedia` | Revient au mode conseiller encyclopédique et historique. |
| `/personas` | Liste les personas disponibles (Empereur, Général, Stratège, Espion). |
| `/persona <id>` | Change la persona active en temps réel. |
| `/audit <chemin.pdf>` | Lance un audit de véracité historique sur un document PDF donné. |
| `/debug on\|off` | Active ou désactive l'affichage verbeux des logs d'ingénierie. |
| `/cache-clear` | Purge la collection du cache sémantique vectoriel dans Qdrant. |
| `/exit` ou `/quit` | Quitte proprement la session CLI. |
