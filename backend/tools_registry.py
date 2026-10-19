import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


def _get_db_conn() -> sqlite3.Connection | None:
    candidates = [
        Path("kingdoms.db"),
        Path("../kingdoms.db"),
        Path("/app/kingdoms.db"),
        Path(__file__).resolve().parent.parent / "kingdoms.db",
    ]
    for p in candidates:
        if p.exists():
            return sqlite3.connect(p)
    return None


def get_kingdom_info(kingdom_name: str) -> Dict[str, Any]:
    """Consulte les faits historiques, la capitale, le souverain et les forces d'un des 7 Royaumes."""
    conn = _get_db_conn()
    if not conn:
        return {"error": "Base de données historique kingdoms.db introuvable.", "code": 404}

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT name, gold, military_power, status FROM kingdoms WHERE LOWER(name) = LOWER(?)",
            (kingdom_name.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return {"error": f"Royaume '{kingdom_name}' introuvable.", "code": 404}

        res = dict(row)
        cur.execute(
            """
            SELECT k2.name, d.relation_status
            FROM diplomacy d
            JOIN kingdoms k1 ON d.kingdom_id_1 = k1.id
            JOIN kingdoms k2 ON d.kingdom_id_2 = k2.id
            WHERE LOWER(k1.name) = LOWER(?) AND d.is_active = 1
            UNION
            SELECT k1.name, d.relation_status
            FROM diplomacy d
            JOIN kingdoms k2 ON d.kingdom_id_2 = k2.id
            JOIN kingdoms k1 ON d.kingdom_id_1 = k1.id
            WHERE LOWER(k2.name) = LOWER(?) AND d.is_active = 1
            """,
            (kingdom_name.strip(), kingdom_name.strip()),
        )
        res["alliances_historiques"] = [{"royaume": r[0], "statut": r[1]} for r in cur.fetchall()]

        # Récupération des unités militaires historiques
        cur.execute(
            """
            SELECT u.unit_name, u.attack, u.defense
            FROM military_units u
            JOIN kingdoms k ON u.kingdom_id = k.id
            WHERE LOWER(k.name) = LOWER(?)
            """,
            (kingdom_name.strip(),),
        )
        res["unites_militaires"] = [dict(u) for u in cur.fetchall()]

        return res
    except Exception as exc:
        return {"error": f"Erreur SQL : {exc}"}
    finally:
        conn.close()


def structured_output(data: Any = None) -> str:
    """Outil: convertit et valide les données au format JSON structuré."""
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
        "description": "Formate et génère une sortie au format JSON structuré strict [T5].",
        "parameters": {
            "data": {"type": "string", "description": "Données ou texte à structurer en JSON"}
        },
        "icon": "Code",
        "category": "Développement",
    },
    {
        "id": "get_kingdom_info",
        "name": "Informations Historiques du Royaume",
        "description": "Consulte les données historiques authentiques, armée, unités et alliances d'un des 7 Royaumes [T1].",
        "parameters": {
            "kingdom_name": {"type": "string", "description": "Nom du royaume (ex: Qin, Zhao, Chu, Han, Wei, Qi, Yan)"}
        },
        "icon": "Database",
        "category": "Histoire de Chine",
    },
]


def list_tools() -> List[Dict[str, Any]]:
    return AVAILABLE_TOOLS


def get_ollama_tools() -> List[Dict[str, Any]]:
    ollama_tools = []
    for tool in AVAILABLE_TOOLS:
        if tool["id"] == "structured_output":
            continue
        properties = {}
        required = []
        for p_name, p_info in tool.get("parameters", {}).items():
            properties[p_name] = {
                "type": p_info.get("type", "string"),
                "description": p_info.get("description", ""),
            }
            required.append(p_name)
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": tool["id"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return ollama_tools


def run_tool(tool_id: str, args: Dict[str, Any]) -> str:
    args = args or {}
    if tool_id in ["structured_output", "Structured Output"]:
        data = args.get("data")
        return structured_output(data)
    if tool_id == "get_kingdom_info":
        name = args.get("kingdom_name") or args.get("name") or ""
        return json.dumps(get_kingdom_info(str(name)), indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Tool '{tool_id}' inconnu"}, indent=2)
