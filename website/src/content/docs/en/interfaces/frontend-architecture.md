---
title: "Frontend Architecture & Protocols"
description: "NDJSON streaming, ask_user_form, Human-in-the-loop and token budget."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/en/frontend-architecture.md"
sidebar:
  order: 3
---
This document details the communication protocols between SensAI's React frontend and FastAPI backend, including NDJSON streaming, dynamic forms, Human-in-the-loop validation, and memory compression.

---

## NDJSON Streaming Protocol (/messages/stream)

Chat communication uses an HTTP `POST` request to `/api/conversations/{id}/messages/stream` returning an `application/x-ndjson` (Newline Delimited JSON) stream.

### Streaming Lifecycle

<pre class="mermaid">
sequenceDiagram
    autonumber
    actor User as User
    participant Front as React Frontend
    participant API as FastAPI Backend
    participant LLM as Ollama Engine
    participant Tools as Tool Registry / MCP

    User-&gt;&gt;Front: Sends user prompt
    Front-&gt;&gt;API: POST /messages/stream
    API--&gt;&gt;Front: Event start (user_message_id)
    
    alt Guardrail Validation Failed
        API--&gt;&gt;Front: Refusal message chunk
        API--&gt;&gt;Front: Event end (completion)
    else Semantic Cache Hit
        API--&gt;&gt;Front: Cached response chunk
        API--&gt;&gt;Front: Event end (from_cache: true)
    else Generation with Tool Call
        API-&gt;&gt;LLM: Inference with compressed history
        LLM--&gt;&gt;API: Tool Call (e.g. calculate_grain_supply)
        API-&gt;&gt;Tools: Synchronous execution (asyncio.to_thread)
        Tools--&gt;&gt;API: JSON output result
        API-&gt;&gt;LLM: Resume generation with tool output
        loop Token Streaming
            LLM--&gt;&gt;API: Delta token
            API--&gt;&gt;Front: Incremental text chunk
        end
        API--&gt;&gt;Front: Event end (token metrics)
    end
</pre>

### Stream Event Types

1. **`{"type": "start", "user_message_id": "<uuid>"}`**: Confirms receipt and logs the stored user message ID.
2. **`{"type": "chunk", "content": "<text>"}`**: Text fragment appended to the current message bubble.
3. **`{"type": "end", "message_id": "<uuid>", "prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165}`**: Stream termination with final usage metrics.

---

## Dynamic Forms (ask_user_form)

When the model lacks necessary parameters to proceed (e.g. target kingdom, duration, manuscript name), it calls the internal tool `ask_user_form`.

### Form Block Format

The backend serializes this call into a delimited markdown code block:

````markdown
```sensai-form
{
  "title": "Military Campaign Setup",
  "fields": [
    {"name": "kingdom", "label": "Target Kingdom", "type": "select", "options": ["Qin", "Zhao", "Chu"]},
    {"name": "soldiers", "label": "Mobilized Troops", "type": "number", "default": 100000}
  ]
}
```
````

### Frontend Rendering

The message component intercepts `sensai-form` code blocks and renders an interactive accessible form:
- Inputs can be modified by the user.
- Upon submission, responses are formatted and sent as the next user message:
  `[Form completed] {"kingdom": "Zhao", "soldiers": 100000}`.
- The AI resumes inference using the exact human-supplied values.

---

## Human-in-the-Loop & Confirmation (sensai-confirm)

Tools with persistent side-effects on disk or database are designated as **destructive actions**:
- `write_manuscript_file` (writing or overwriting markdown files).
- `update_kingdom_database` (direct SQL execution in `kingdoms.db`).

### Ephemeral Token Locking

1. **Detection:** When the model calls a destructive tool, execution pauses immediately.
2. **Escrow:** The backend generates an ephemeral cryptographic `action_id` and saves the pending call in memory.
3. **Block `sensai-confirm`:** Emits a formatted confirmation block:
   ````markdown
   ```sensai-confirm
   {
     "tool": "write_manuscript_file",
     "action_id": "sec_tok_9f8a3b12",
     "summary": "Write into manuscript 'chroniques_qin.md' (340 characters)"
   }
   ```
   ````
4. **User Action:** The frontend displays an approval card with two actions: **Approve** or **Reject**.
5. **Execution:** If approved, the subsequent request passes `approval_token: "sec_tok_9f8a3b12"`. The backend verifies the token and executes the action.

---

## Token Budgeting & Semantic Compression

To avoid overflowing local context windows (`qwen2.5` or `llama3`), the backend enforces memory budgeting (`memory_management.py`):

- **Configurable Limit:** Default maximum history budget (`HISTORY_TOKEN_BUDGET = 4000` tokens).
- **Automated Compression:** When history exceeds this limit, older messages are summarized in the background by a lightweight LLM sub-call.
- **Recent Turn Preservation:** The most recent turns remain untouched to preserve conversational coherence.
