import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

TOOLS_METADATA = [
    {
        "name": "calculate_grain_supply",
        "description": "Calcule la quantité de grain nécessaire pour entretenir une armée en campagne militaire.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kingdom": {
                    "type": "string",
                    "description": "Nom du royaume (ex: Qin, Zhao, Chu).",
                },
                "soldiers": {
                    "type": "integer",
                    "description": "Nombre de soldats mobilisés.",
                },
                "months": {
                    "type": "integer",
                    "description": "Durée prévue de la campagne en mois.",
                    "default": 3,
                },
            },
            "required": ["kingdom", "soldiers"],
        },
    },
    {
        "name": "get_historical_battle",
        "description": "Fournit les détails tactiques et stratégiques d'une bataille majeure des Royaumes Combattants.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "battle_name": {
                    "type": "string",
                    "description": "Nom de la bataille (ex: Changping, Handan, Guiling, Maling, Yique).",
                },
            },
            "required": ["battle_name"],
        },
    },
]

HISTORICAL_BATTLES = {
    "changping": {
        "name": "Bataille de Changping",
        "year": "-260",
        "belligerents": ["Qin", "Zhao"],
        "commanders": {"Qin": "Bai Qi", "Zhao": "Zhao Kuo"},
        "outcome": "Victoire décisive de Qin. Encerclement et massacre de l'armée de Zhao.",
        "significance": "Affaiblissement irrémédiable de l'état de Zhao, ouvrant la voie à l'unification.",
    },
    "handan": {
        "name": "Siège de Handan",
        "year": "-257",
        "belligerents": ["Qin", "Zhao", "Wei", "Chu"],
        "commanders": {"Qin": "Wang Ling", "Coalition": "Seigneur Pingyuan, Seigneur Xinling"},
        "outcome": "Victoire de la coalition alliée, retraite de l'armée de Qin.",
        "significance": "Ralentit temporairement l'expansionnisme de Qin.",
    },
    "guiling": {
        "name": "Bataille de Guiling",
        "year": "-354",
        "belligerents": ["Qi", "Wei"],
        "commanders": {"Qi": "Tian Ji et Sun Bin", "Wei": "Pang Juan"},
        "outcome": "Victoire de Qi via la tactique légendaire 'Assiéger Wei pour sauver Zhao'.",
        "significance": "Établit le génie militaire de Sun Bin.",
    },
    "maling": {
        "name": "Bataille de Maling",
        "year": "-342",
        "belligerents": ["Qi", "Wei"],
        "commanders": {"Qi": "Tian Ji et Sun Bin", "Wei": "Pang Juan"},
        "outcome": "Embuscade décisive de Qi, mort du général Pang Juan.",
        "significance": "Fin de l'hégémonie militaire du royaume de Wei.",
    },
    "yique": {
        "name": "Bataille de Yique",
        "year": "-293",
        "belligerents": ["Qin", "Han", "Wei"],
        "commanders": {"Qin": "Bai Qi", "Coalition": "Gongsun Xi"},
        "outcome": "Victoire écrasante de Qin, 240 000 têtes ennemies coupées.",
        "significance": "Élimination des forces de pointe de Han et Wei.",
    },
}


def _execute_calculate_grain_supply(args: dict[str, Any]) -> dict[str, Any]:
    kingdom = str(args.get("kingdom", "Inconnu")).strip()
    soldiers = int(args.get("soldiers", 0))
    months = int(args.get("months", 3))

    if soldiers <= 0:
        return {"error": "Le nombre de soldats doit être strictement supérieur à zéro."}

    grain_per_soldier_month = 0.045
    total_grain_tons = round(soldiers * months * grain_per_soldier_month, 2)
    daily_caravan_carts = max(1, int(soldiers / 250))

    return {
        "kingdom": kingdom,
        "soldiers": soldiers,
        "campaign_months": months,
        "total_grain_tons": total_grain_tons,
        "estimated_supply_carts_per_day": daily_caravan_carts,
        "status": "Logistique validée pour la campagne.",
    }


def _execute_get_historical_battle(args: dict[str, Any]) -> dict[str, Any]:
    raw_query = str(args.get("battle_name", "")).strip().lower()
    for key, data in HISTORICAL_BATTLES.items():
        if key in raw_query or raw_query in key:
            return data

    return {
        "searched": raw_query,
        "error": f"Bataille '{raw_query}' non répertoriée dans les archives des Royaumes Combattants.",
        "available_battles": list(HISTORICAL_BATTLES.keys()),
    }


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "warring-states-mcp-server",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS_METADATA},
        }

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "calculate_grain_supply":
            data = _execute_calculate_grain_supply(arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "isError": "error" in data,
                },
            }

        if tool_name == "get_historical_battle":
            data = _execute_get_historical_battle(arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "isError": "error" in data,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Outil '{tool_name}' non supporté par ce serveur MCP.",
            },
        }

    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Méthode '{method}' non supportée."},
        }

    return None


def main() -> None:
    for line in sys.stdin:
        line_clean = line.strip()
        if not line_clean:
            continue
        try:
            req = json.loads(line_clean)
        except json.JSONDecodeError:
            continue

        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
