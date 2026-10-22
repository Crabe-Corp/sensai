import json
from typing import Any

from src.features.sec.permissions import safe_read, safe_write
from src.features.tools.registry import ToolRegistry, tool
from .human_verif import Change, confirm_simple, review_changes
from .kingdom_fight import resolve_battle
from .report import build_report
from .store import Simulation

simulation_registry = ToolRegistry()
_sim: Simulation | None = None
NO_SIM = {"error": "Aucune simulation active. L'utilisateur doit taper /simulation."}
EVENT_LIMITS = {"troops": 0.25, "gold": 0.30, "morale": 30}

def start(seed: int | None = None) -> Simulation:
    global _sim
    stop()
    _sim = Simulation(seed)
    return _sim

def stop() -> None:
    global _sim
    if _sim:
        _sim.close()
        _sim = None

@tool(registry=simulation_registry)
def list_kingdoms() -> dict[str, Any]:
    """Liste l'état courant de tous les royaumes de la simulation (troupes, moral, or, statut).
            PARAMS: Aucun
            RETURN: dictionnaire contenant la liste des royaumes"""
    return {"kingdoms": _sim.kingdoms()} if _sim else NO_SIM

@tool(registry=simulation_registry)
def get_kingdom_state(kingdom: str) -> dict[str, Any]:
    """Donne l'état d'un royaume et son meilleur général actif.
            PARAMS: - kingdom - STR: nom du royaume
            RETURN: dictionnaire avec les statistiques et le général, ou une erreur"""
    if not _sim:
        return NO_SIM
    k = _sim.get_kingdom(kingdom)
    if not k:
        return {"error": f"Royaume inconnu. Disponibles : {_sim.names()}"}
    return {**k, "best_general": _sim.best_general(k["id"])}

@tool(registry=simulation_registry)
def simulate_battle(attacker: str, defender: str) -> dict[str, Any]:
    """Lance une bataille entre deux royaumes. Les chiffres sont calculés par le code, puis validés par l'utilisateur.
            PARAMS: - attacker - STR: nom du royaume attaquant
                    - defender - STR: nom du royaume défenseur
            RETURN: résumé de la bataille (vainqueur, pertes, général tombé) ou statut rejected"""
    if not _sim:
        return NO_SIM
    a, b = _sim.get_kingdom(attacker), _sim.get_kingdom(defender)
    if not a or not b:
        return {"error": f"Royaume inconnu. Disponibles : {_sim.names()}"}
    if a["id"] == b["id"]:
        return {"error": "Un royaume ne peut pas se combattre lui-même."}
    if "annexed" in (a["status"], b["status"]):
        return {"error": "Un des royaumes est déjà annexé."}

    changes, summary = resolve_battle(a, _sim.best_general(a["id"]), b, _sim.best_general(b["id"]),
                                      seed=_sim.seed + _sim.turn)
    accepted = review_changes(f"{a['name']} attaque {b['name']} (victoire de {summary['winner']})", changes)
    if not accepted:
        return {"status": "rejected", "message": "L'utilisateur a refusé tous les changements. Rien n'a été enregistré."}
    _sim.apply(accepted)
    _sim.log("battle", json.dumps(summary, ensure_ascii=False))
    _sim.turn += 1
    return {"status": "applied", "applied": len(accepted), "rejected": len(changes) - len(accepted), "summary": summary}

@tool(registry=simulation_registry)
def propose_event(kingdom: str, field: str, delta: int, reason: str) -> dict[str, Any]:
    """Propose un événement hors bataille (famine, trahison, réforme) modifiant un royaume.
            PARAMS: - kingdom - STR: nom du royaume touché
                    - field - STR: champ modifié, parmi troops, morale ou gold
                    - delta - INT: variation à appliquer, négative pour une perte
                    - reason - STR: cause narrative de l'événement
            RETURN: statut de l'application ou motif du refus"""
    if not _sim:
        return NO_SIM
    k = _sim.get_kingdom(kingdom)
    if not k:
        return {"error": f"Royaume inconnu. Disponibles : {_sim.names()}"}
    if field not in EVENT_LIMITS:
        return {"error": f"Champ invalide. Choisir parmi {list(EVENT_LIMITS)}."}
    max_abs = EVENT_LIMITS[field] if field == "morale" else int(k[field] * EVENT_LIMITS[field])
    if abs(delta) > max_abs:
        return {"error": f"delta trop grand : maximum ±{max_abs} pour {field} de {k['name']}."}
    new = k[field] + delta
    new = max(0, min(100, new)) if field == "morale" else max(0, new)
    accepted = review_changes(f"Événement : {reason}", [Change("sim_kingdoms", k["id"], field, k[field], new, reason)])
    if not accepted:
        return {"status": "rejected", "message": "L'utilisateur a refusé l'événement."}
    _sim.apply(accepted)
    _sim.log("event", f"{k['name']} {field} {delta:+d} : {reason}")
    _sim.turn += 1
    return {"status": "applied", "kingdom": k["name"], field: new}

@tool(registry=simulation_registry)
def get_simulation_facts() -> dict[str, Any]:
    """Récupère le bilan chiffré de la simulation (batailles, généraux tombés, état final).
            PARAMS: Aucun
            RETURN: dictionnaire des faits tirés du journal de simulation"""
    return _sim.facts() if _sim else NO_SIM

@tool(registry=simulation_registry)
def write_battle_report(path: str, analysis: str) -> dict[str, Any]:
    """Écrit le rapport de fin de simulation dans le dossier autorisé. Le bilan chiffré est ajouté automatiquement.
            PARAMS: - path - STR: chemin du rapport, sous rapports_batailles/ (ex. rapports_batailles/changping.md)
                    - analysis - STR: analyse tactique rédigée par l'agent en markdown
            RETURN: statut de l'écriture ou raison du refus"""
    if not _sim:
        return NO_SIM
    content = build_report(_sim.facts(), analysis)
    return safe_write(path, content, confirm_overwrite=lambda: confirm_simple(f"Écraser {path} ?"))

@tool(registry=simulation_registry)
def read_battle_report(path: str) -> dict[str, Any]:
    """Relit un rapport de simulation déjà enregistré.
            PARAMS: - path - STR: chemin du rapport, sous rapports_batailles/ (ex. rapports_batailles/changping.md)
            RETURN: contenu du rapport ou raison du refus"""
    return safe_read(path)
