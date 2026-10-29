---
title: "Guide du Contributeur"
description: "Conventions de code, contributeurs, standards de test et cycle de vie des PRs."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/contributing.md"
sidebar:
  order: 1
---
Bienvenue dans l'équipe des contributeurs de **SensAI** ! Ce document résume les standards d'ingénierie, les règles de style de code et le cycle de vie des contributions.

---

## 👥 Équipe du Projet

| Contributeur | Profil GitHub | Rôle |
| :--- | :--- | :--- |
| **Lucas Lhomme** | [@LucasLhomme](https://github.com/LucasLhomme) | Lead Architect / Core Developer |
| **Graig Ware** | [@graigware](https://github.com/graigware) | Core Contributor |
| **Jawed Lahrouri** | [@jawedlahrouri](https://github.com/jawedlahrouri) | Core Contributor |
| **Jo Birck** | [@jobirck](https://github.com/jobirck) | Contributor / Project Owner |

---

## 📐 Standards de Code & Architecture

### 1. Python (Backend & Moteur Core)

- **Typage Strict :** Utilisez systématiquement les annotations de type (`typing.Optional`, `list[str]`, `dict[str, Any]`, etc.).
- **Asynchronisme Propre :** Les appels bloquants (E/S disques, requêtes SQL synchrones, requêtes HTTP lourdes vers Ollama ou le Web) exécutés dans les routes FastAPI doivent impérativement être délégués à un thread pool via `await asyncio.to_thread(...)` pour ne jamais bloquer la boucle d'événements principale.
- **Gestion des Erreurs :** Ne capturez jamais d'exceptions génériques sans logger l'erreur via le module `logging`.
- **Linter & Formatteur :** Respectez les règles PEP 8 / Flake8 / Ruff.

### 2. Frontend (React 19 & shadcn/ui)

- **Direction Artistique :** Appliquez strictement les principes Dark Obsidian inspirés de Linear.app et Dub.co.
- **Interdictions Visuelles :** Pas de dégradés multicolores, pas de couleurs fluo criardes, pas d'effets glassmorphism excessifs, pas d'emojis dans les boutons ou titres.
- **Accessibilité :** Privilégiez les primitives accessibles de `@base-ui/react` et shadcn/ui.
- **Linter :** Exécutez `npm run lint` avec **Oxlint** avant chaque commit.

### 3. Modern C++ (Extensions Systèmes & SDK)

Si vous développez des extensions natives ou des bibliothèques C++ pour SensAI :
- **RAII Strict :** Aucun `new` ou `delete` brut. Utilisez systématiquement `std::unique_ptr` ou `std::shared_ptr`.
- **Règle de 0 :** Privilégiez la gestion automatique des ressources via les conteneurs standard.
- **Encapsulation & Const-correctness :** Membres privés, méthodes `const`, et utilisation systématique d'`override` et `final`.
- **Pas de macros du C :** Préférez `constexpr` et les constantes typées.

---

## 🧪 Tests & Qualité

Avant d'ouvrir une Pull Request, assurez-vous que l'ensemble de la suite de tests est au vert :

```bash
# Tests unitaires et d'intégration backend (Python)
pytest -v

# Vérification du typage et du build frontend
cd frontend
npm run lint
npm run build
```

---

## 🔄 Cycle de Vie d'une Pull Request (PR Checklist)

1. **Branche de travail :** Créez une branche explicite à partir de `dev` (ex: `feature/nom-de-feature` ou `fix/nom-du-bug`).
2. **Commits atomiques :** Utilisez la convention des commits conventionnels (ex: `feat(core): ...`, `fix(web): ...`, `docs: ...`).
3. **Mise à jour de la documentation :** Si vous modifiez un comportement visible ou ajoutez un outil, documentez-le dans le dossier `docs/`.
4. **CI Verte :** Vérifiez que tous les jobs GitHub Actions passent avec succès.
