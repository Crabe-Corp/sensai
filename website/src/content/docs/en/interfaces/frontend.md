---
title: "SensAI Web Frontend"
description: "React 19 web interface, Tailwind v4, shadcn/ui and Dark Obsidian design."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/en/frontend.md"
sidebar:
  order: 2
---
SensAI's web interface delivers a modern, reactive cockpit for interacting with local LLMs, administrating MCP tools, and monitoring conversation memory states.

---

## Art Direction & Design System

The SensAI user interface adheres to a clean, technical, high-density art direction inspired by **Linear.app** and **Dub.co**:

- **Dark Obsidian Palette:** Deep backgrounds (`#09090b` / `#0c0d0e`), subtle elevated surfaces (`#121316` / `#16181d`), and crisp 1px borders (`border-border` / `border-zinc-800`).
- **Typographic Precision:** Native system sans-serif font stack with high information density, strict geometric alignments, and refined micro-details.
- **Controlled Micro-Interactions:** Tight corner radii (`rounded-md` / `rounded-lg`, ~6-8px), free of heavy drop shadows, neon blobs, or distracting animations.
- **shadcn/ui Primitives:** Built on accessible `@base-ui/react` primitives and styled with Tailwind CSS v4.

---

## Technical Stack

<pre class="mermaid">
flowchart LR
    subgraph Client ["Frontend Browser"]
        React["React 19"]
        Vite["Vite 8"]
        Tailwind["Tailwind CSS v4"]
        shadcn["shadcn / UI"]
        Lucide["Lucide React Icons"]
    end

    subgraph API ["FastAPI Backend"]
        Auth["Auth JWT"]
        Streaming["NDJSON Streaming SSE"]
        ConvRoutes["Conversation Routes"]
        ToolBridge["Tools Bridge"]
    end

    Client --&gt;|"HTTP / Bearer Token"| Auth
    Client --&gt;|"POST /messages/stream"| Streaming
    Streaming --&gt; ConvRoutes
    ConvRoutes --&gt; ToolBridge
</pre>

| Component | Technology | Version / Details |
| :--- | :--- | :--- |
| **UI Framework** | React | `^19.2.8` |
| **Bundler & Tooling** | Vite | `^8.3.0` |
| **Styling** | Tailwind CSS v4 | `@tailwindcss/vite ^4.3.3` |
| **Components** | shadcn/ui & Base UI | `@base-ui/react ^1.8.0`, `shadcn ^4.21.3` |
| **Icons** | Lucide React | `^1.52.0` |
| **Linter** | Oxlint | `^1.81.0` (Rust-based) |

---

## Key Interface Features

1. **Fluid Token Streaming (SSE / NDJSON):** Tokens stream word-by-word without UI blocking, with automatic end-of-stream detection.
2. **Model Manager:** Dynamic inference model selector (e.g. `qwen2.5:7b`, `qwen2.5:3b`, `llama3:8b`) with user-level persistence.
3. **Modular Tool Picker:** Popover menu to toggle active tools on the fly:
   - *Structured Output* (strict JSON formatting).
   - *Live Web Search* (DuckDuckGo / Wikipedia).
   - *PDF Document Generation*.
   - *External tools connected via Model Context Protocol (MCP)*.
4. **Interactive Inline Forms (`sensai-form`):** When the AI needs missing parameters, it emits an interactive form block with inputs (text, numbers, selects) filled directly within the chat stream.
5. **Human-in-the-Loop Confirmation (`sensai-confirm`):** For destructive operations (disk file writing or database modification), the UI presents a confirmation card with a single-use approval token.
6. **Token Budget Counter:** Real-time display of request costs (prompt tokens, completion tokens, and cumulative total).
