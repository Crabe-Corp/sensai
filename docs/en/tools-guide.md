# Tool Development & MCP Integration Guide

SensAI provides a modular tool architecture allowing developers to extend agent capabilities with native Python tools or remote servers via Anthropic's **Model Context Protocol (MCP)**.

---

## Creating a Native Tool with the `@tool` Decorator

Native tools reside in `src/features/tools/`. To declare a new tool:

### 1. Function Declaration

Use the `@tool` decorator imported from `src.features.tools.registry`. Type annotations and docstrings are inspected to build the JSON schema sent to Ollama:

```python
# src/features/tools/army_morale.py
from typing import Any, Dict
from src.features.tools.registry import tool

@tool
def evaluate_army_morale(kingdom: str, unpaid_months: int = 0) -> Dict[str, Any]:
    """Evaluates the combat readiness and morale of an army based on current conditions.
    
    PARAMS:
        - kingdom - STR: Kingdom name (e.g. Qin, Chu, Zhao)
        - unpaid_months - INT: Number of months soldiers have gone without pay
        
    RETURN:
        - Dictionary containing morale rating and mutiny risk
    """
    if unpaid_months > 3:
        return {
            "kingdom": kingdom,
            "morale": "critical",
            "score": 25,
            "mutiny_risk": "very high",
            "advice": "Pay soldiers immediately to prevent mutiny."
        }
    
    return {
        "kingdom": kingdom,
        "morale": "good",
        "score": 85,
        "mutiny_risk": "low",
        "advice": "Troops are ready for military deployment."
    }
```

### 2. Registration in the Default Registry

In `src/features/tools/__init__.py` or `builtin.py`, ensure the module is imported so that `@tool` registers with `default_registry`:

```python
from . import army_morale
```

### 3. Exposing Tools in the Web Interface

In `backend/tools_registry.py`:
1. Map a Lucide icon and category in `_TOOL_UI`:
   ```python
   _TOOL_UI["evaluate_army_morale"] = ("ShieldAlert", "Military")
   ```
2. If the tool is a destructive operation (disk writing or deletion), add its name to `DESTRUCTIVE_TOOLS`:
   ```python
   DESTRUCTIVE_TOOLS.add("my_destructive_tool")
   ```
3. If the tool is an internal read-only tool always available to the model, add it to `READ_ONLY_TOOLS`:
   ```python
   READ_ONLY_TOOLS.add("evaluate_army_morale")
   ```

---

## External MCP Server Integration

SensAI implements the standard **Model Context Protocol (MCP)** client (`src/features/tools/mcp_client.py`) communicating over standard input/output (`stdio`).

### Demo MCP Server Structure

A complete reference is located in `src/features/tools/mcp_server_demo.py`:

```python
# MCP server excerpt
import json
import sys

TOOLS_METADATA = [
    {
        "name": "calculate_grain_supply",
        "description": "Calculates grain supply requirements for an army campaign.",
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
        return {"content": [{"type": "text", "text": "..."}]}
```

### Dynamic Connection via API

Connect MCP servers at runtime without restarting the backend:

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

The backend discovers exposed tools via `tools/list` and injects them into the `ToolRegistry`. They become immediately visible in the frontend tool selector.

---

## Security Best Practices

1. **No Raw SQL:** Use parameterized queries via SQLite / SQLAlchemy to prevent SQL injection.
2. **Path Confinement:** Prevent path traversal by validating that file operations remain strictly within allowed directories (`manuscrit_royaumes/`, `exports/`).
3. **Explicit Type Constraints:** Specify exact types (`int`, `str`, `float`, `list[str]`) so Ollama produces compliant arguments during function calling.
