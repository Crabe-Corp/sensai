---
title: SensAI
description: Modular, agentic AI assistant inspired by the 7 Warring States of Ancient China.
template: splash
editUrl: false
hero:
  title: SensAI
  tagline: Modular, sovereign and agentic AI assistant. Explore ancient historical chronicles or launch turn-based tactical war simulations.
  image:
    file: ../../../assets/logo.svg
  actions:
    - text: Explore the Project
      link: /sensai/en/overview/
      icon: right-arrow
    - text: CLI Guide
      link: /sensai/en/interfaces/cli/
      icon: laptop
      variant: secondary
    - text: Web Frontend
      link: /sensai/en/interfaces/frontend/
      icon: document
      variant: minimal
    - text: GitHub
      link: https://github.com/Crabe-Corp/sensai
      icon: external
      variant: minimal
---

## Two Interfaces, One Sovereign Engine

SensAI combines two complementary interfaces built to explore the history of Ancient China's 7 Warring States:

- **SensAI CLI**: The foundational roleplaying terminal featuring proactive RAG chronicle retrieval (*Shiji*, *Zhan Guo Ce*) and interactive turn-based tactical battle simulation (`/simulation [seed]`).
- **SensAI Web Frontend**: A high-density modern cockpit built with React 19 and shadcn/ui, featuring token-by-token SSE streaming, dynamic interactive forms (`sensai-form`), Human-in-the-loop cryptographic action validation, and live token budget counters.