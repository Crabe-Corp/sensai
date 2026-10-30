---
title: SensAI
description: Assistant IA modulaire et agentique inspiré des 7 Royaumes Combattants de la Chine antique.
template: splash
editUrl: false
hero:
  title: SensAI
  tagline: Assistant IA modulaire, agentique et souverain. Explorez le lore historique des 7 Royaumes Combattants ou lancez des simulations de guerre tactiques.
  image:
    file: ../../../assets/logo.svg
  actions:
    - text: Découvrir le projet
      link: /sensai/fr/overview/
      icon: right-arrow
    - text: Guide du CLI
      link: /sensai/fr/interfaces/cli/
      icon: laptop
      variant: secondary
    - text: Interface Frontend
      link: /sensai/fr/interfaces/frontend/
      icon: document
      variant: minimal
    - text: GitHub
      link: https://github.com/Crabe-Corp/sensai
      icon: external
      variant: minimal
---

## Deux interfaces, un moteur souverain

SensAI combine deux interfaces complémentaires développées pour explorer l'histoire des Sept Royaumes Combattants de la Chine antique :

- **SensAI CLI** : Le terminal de référence pour le rôle immersif, l'enrichissement RAG automatique dans les chroniques antiques (*Shiji*, *Zhan Guo Ce*) et la simulation de batailles tactiques au tour par tour (`/simulation [seed]`).
- **SensAI Web Frontend** : Cockpit graphique moderne en React 19 et shadcn/ui, offrant le streaming SSE temps-réel, les formulaires interactifs (`sensai-form`), la validation sécurisée des actions sensibles (*Human-in-the-loop*) et le suivi en direct du budget de tokens.