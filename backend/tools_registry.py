import json
from typing import Any, Dict, List


def structured_output(data: Any = None) -> str:
    """Outil fait main: convertit et renvoie les données au format JSON structuré."""
    try:
        if data is None:
            return json.dumps({"status": "success", "message": "Structured output généré avec succès"}, indent=2, ensure_ascii=False)
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                return json.dumps({"output": data}, indent=2, ensure_ascii=False)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Erreur de formatage JSON: {str(e)}"}, indent=2)


AVAILABLE_TOOLS = [
    {
        "id": "structured_output",
        "name": "Structured Output",
        "description": "Formate et génère une sortie au format JSON structuré.",
        "parameters": {
            "data": {"type": "string", "description": "Données à formater en JSON"}
        },
        "icon": "Code",
        "category": "Développement"
    }
]


def list_tools() -> List[Dict[str, Any]]:
    return AVAILABLE_TOOLS


def run_tool(tool_id: str, args: Dict[str, Any]) -> str:
    if tool_id in ["structured_output", "Structured Output"]:
        data = args.get("data") if args else None
        return structured_output(data)
    return json.dumps({"error": f"Tool '{tool_id}' inconnu"}, indent=2)
