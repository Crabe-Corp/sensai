---
title: "SensAI CLI Guide"
description: "Commands, options, /encyclopedia and /simulation modes."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/en/cli.md"
sidebar:
  order: 1
---
The command-line interface (CLI) is the foundational execution engine of SensAI. It provides token streaming, pre-generation RAG context enrichment from ancient manuscripts, and a full turn-based tactical battle simulator.

---

## Launch & Options

To start the CLI, run the main module from the repository root:

```bash
python -m src.interfaces.cli.main [OPTIONS]
```

### Command-Line Arguments

| Option | Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--model` | `-m` | `str` | `llama3` | Name of the Ollama model to use (recommended: `qwen2.5:7b`). |
| `--host` | | `str` | `http://localhost:11434` | Base URL of the Ollama server. |
| `--max-tokens` | `-t` | `int` | `32768` | Context window token budget for the session. |
| `--tools` | | `bool` | `False` | Enables local tools and the MCP demo server. |
| `--profile` | `-p` | `str` | `None` | Loads a specific user history profile. |
| `--rag` | | `bool` | `True` | Enables automated RAG document enrichment in Qdrant. |
| `--debug` | | `bool` | `False` | Displays internal execution logs, similarity scores, and RAG details. |

---

## Operating Modes

The CLI provides two primary modes toggled via slash commands:

<pre class="mermaid">
stateDiagram-v2
    [*] --&gt; Encyclopedia : Default launch
    Encyclopedia --&gt; Simulation : /simulation [seed]
    Simulation --&gt; Encyclopedia : /encyclopedia
    Encyclopedia --&gt; [*] : /exit
    Simulation --&gt; [*] : /exit
</pre>

### 1. Encyclopedia Mode (`/encyclopedia`) — Default Mode

In Encyclopedia mode, the agent acts as a **Grand Imperial Advisor and scholar of the 7 Warring States**.

- **Automatic Pre-Generation RAG:** Every user query triggers a hybrid search in the Qdrant vector database (`retriever.py`). Authentic excerpts from ancient chronicles (*Shiji*, *Zhan Guo Ce*) are injected directly into the model context before inference.
- **Embedded Historical Rules:**
  - **Military Unit Correction (Wan x10):** Ancient texts translate the Chinese numeral unit "Wan" (10,000) literally (e.g. 20,000). The model adjusts troop sizes to reflect historical reality (e.g. 200,000 soldiers).
  - **Anti-Confusion:** Prevents mix-ups between historical figures with similar names (e.g. Li Xin vs Han Xin vs Wang Jian).
  - **Graceful Web Fallback:** If local chronicles lack coverage, the CLI performs a fallback web search (*DuckDuckGo* / *Wikipedia*) without hallucination.

### 2. Simulation Mode (`/simulation [seed]`)

Simulation mode turns the agent into a **War Master** overseeing a turn-based wargame between the 7 kingdoms (Qin, Chu, Qi, Zhao, Wei, Han, Yan).

- **Free chat disabled (`free_chat: False`):** The model cannot state any number, casualty, or outcome that is not derived directly from a verified tool call (`simulate_battle`, `get_kingdom_state`, `list_kingdoms`).
- **Reproducible Seed:** Allows replaying campaigns with identical initial conditions.
- **Structured Battle Reports:** The agent synthesizes casualties, territorial changes, and supply logistics based strictly on simulation facts.

---

## Available Commands

| Command | Description |
| :--- | :--- |
| `/help` | Displays the list of available commands and flags. |
| `/simulation [seed]` | Switches to battle simulation mode with a fresh game state. |
| `/encyclopedia` | Returns to the scholarly encyclopedia advisor mode. |
| `/personas` | Lists available personas (Emperor, General, Strategist, Spy). |
| `/persona <id>` | Switches the active persona in real time. |
| `/audit <path.pdf>` | Runs a historical veracity audit on a given PDF document. |
| `/debug on\|off` | Toggles detailed engineering debug logs. |
| `/cache-clear` | Clears the semantic vector cache collection in Qdrant. |
| `/exit` or `/quit` | Exits the CLI session cleanly. |
