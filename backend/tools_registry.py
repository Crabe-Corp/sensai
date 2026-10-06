import json
import random
import re
from typing import Any, Dict, List


def get_kingdom_info(name: str) -> Dict[str, Any]:
    """Outil fait main: interroge les statistiques d'un royaume (factions de SensAI)."""
    # Valeurs fictives / basées sur le lore des 7 Royaumes de SensAI
    kingdoms = {
        "valoria": {"gold": 15400, "military_power": 8500, "status": "Prospère", "ruler": "Archiduc Valen"},
        "draconis": {"gold": 8200, "military_power": 14200, "status": "En alerte de guerre", "ruler": "Général Ignis"},
        "aethelgard": {"gold": 22000, "military_power": 6100, "status": "Paix commerciale", "ruler": "Reine Seraphina"},
        "solaria": {"gold": 12000, "military_power": 9000, "status": "Stabilité", "ruler": "Roi Aurelius"},
        "umbra": {"gold": 9400, "military_power": 11000, "status": "Tensions frontalières", "ruler": "Ombremaître Vane"},
    }
    key = name.lower().strip()
    for k, v in kingdoms.items():
        if k in key:
            return {"found": True, "kingdom": k.capitalize(), "data": v}
    return {
        "found": True,
        "kingdom": name.capitalize(),
        "data": {
            "gold": random.randint(5000, 25000),
            "military_power": random.randint(4000, 15000),
            "status": "Neutre",
            "ruler": f"Seigneur de {name.capitalize()}"
        }
    }


def roll_dice(notation: str) -> Dict[str, Any]:
    """Outil fait main: lanceur de dés JDR (ex: 1d20+4, 2d6, 1d100)."""
    pattern = r"^(\d+)d(\d+)(?:([+-])(\d+))?$"
    match = re.match(pattern, notation.strip().lower())
    if not match:
        rolls = [random.randint(1, 20)]
        return {"notation": "1d20", "rolls": rolls, "modifier": 0, "total": rolls[0]}

    count = int(match.group(1))
    sides = int(match.group(2))
    sign = match.group(3)
    mod = int(match.group(4)) if match.group(4) else 0

    count = min(count, 50)  # Sécurité
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if sign == "+":
        total += mod
    elif sign == "-":
        total -= mod

    return {
        "notation": notation,
        "rolls": rolls,
        "modifier": f"{sign}{mod}" if sign else "0",
        "total": total
    }


def calculate_math(expression: str) -> Dict[str, Any]:
    """Outil fait main: calculatrice sécurisée."""
    clean_expr = re.sub(r"[^0-9+\-*/().\s]", "", expression)
    try:
        # Évaluation sécurisée limitée aux maths simples
        result = eval(clean_expr, {"__builtins__": None}, {})
        return {"expression": expression, "result": result, "status": "success"}
    except Exception as e:
        return {"expression": expression, "error": str(e), "status": "error"}


AVAILABLE_TOOLS = [
    {
        "id": "kingdom_stats",
        "name": "Statistiques des Royaumes",
        "description": "Consulte les ressources (or, armée, statut diplomatique) d'un royaume de SensAI.",
        "parameters": {
            "name": {"type": "string", "description": "Nom du royaume (ex: Valoria, Draconis, Solaria)"}
        },
        "icon": "Crown",
        "category": "Lore & Base de données"
    },
    {
        "id": "dice_roller",
        "name": "Lanceur de dés JDR",
        "description": "Effectue des tirages de dés (ex: 1d20, 2d6+3, 1d100) pour tester des actions ou duels.",
        "parameters": {
            "notation": {"type": "string", "description": "Notation du dé (ex: 1d20+5, 2d6)"}
        },
        "icon": "Dice5",
        "category": "Jeu de rôle"
    },
    {
        "id": "calculator",
        "name": "Calculateur d'armée & tributs",
        "description": "Effectue des calculs arithmétiques pour la gestion des tributs, pertes militaires et taxes.",
        "parameters": {
            "expression": {"type": "string", "description": "Expression mathématique à évaluer"}
        },
        "icon": "Calculator",
        "category": "Outils tactiques"
    }
]


def list_tools() -> List[Dict[str, Any]]:
    return AVAILABLE_TOOLS


def run_tool(tool_id: str, args: Dict[str, Any]) -> str:
    if tool_id == "kingdom_stats":
        res = get_kingdom_info(args.get("name", "Valoria"))
        return f"[Tool: Statistiques de {res['kingdom']}] Or: {res['data']['gold']} pièces, Armée: {res['data']['military_power']} soldats, Statut: {res['data']['status']}, Dirigeant: {res['data']['ruler']}."
    elif tool_id == "dice_roller":
        res = roll_dice(args.get("notation", "1d20"))
        return f"[Tool: Lancer de dés {res['notation']}] Tirages: {res['rolls']}, Modificateur: {res['modifier']} -> Total: {res['total']}."
    elif tool_id == "calculator":
        res = calculate_math(args.get("expression", "0"))
        if res.get("status") == "success":
            return f"[Tool: Calculateur] Résultat de '{res['expression']}' = {res['result']}."
        return f"[Tool: Calculateur] Erreur dans le calcul: {res.get('error')}."
    return f"[Tool: {tool_id}] Outil inconnu."

