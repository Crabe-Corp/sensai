import json
from typing import Any

from src.features.sec.permissions import safe_read, safe_write
from src.features.tools.registry import ToolRegistry, tool
from .human_verif import confirm_simple, review_changes
from .kingdom_fight import resolve_battle
from .report import build_report
from .store import Simulation

simulation_registry = ToolRegistry()
_sim: Simulation | None = None
NO_SIM = {"error": "Aucune simulation active. L'utilisateur doit taper /simulation."}

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
    """Lance une bataille entre deux royaumes. À appeler dès que l'utilisateur parle d'attaque, de combat, de bataille ou de guerre.
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
    pertes = ", ".join(f"{k} {v:,}" for k, v in summary["casualties"].items())
    fell = f"Le général {summary['general_fallen']} est tombé." if summary["general_fallen"] else "Aucun général tombé."
    faits = (f"{summary['winner']} a battu {summary['loser']}. Pertes : {pertes}. {fell} "
             f"{len(accepted)} changement(s) appliqué(s) sur {len(changes)}.")
    return {"status": "applied", "applied": len(accepted), "rejected": len(changes) - len(accepted),
            "summary": summary, "faits": faits}


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
                    - analysis - STR: analyse tactique rédigée par l'agent en markdown, uniquement à partir de get_simulation_facts
            RETURN: statut de l'écriture ou raison du refus"""
    if not _sim:
        return NO_SIM
    facts = _sim.facts()
    if facts["turns"] == 0:
        return {"status": "error", "reason": "Aucune bataille n'a eu lieu : lance d'abord simulate_battle."}
    content = build_report(facts, analysis)

    def confirm(exists: bool) -> bool:
        print(f"\n[APERÇU DU RAPPORT → {path}]\n{content}")
        return confirm_simple(f"Écraser {path} ?" if exists else f"Enregistrer {path} ?")

    return safe_write(path, content, confirm=confirm)


@tool(registry=simulation_registry)
def read_battle_report(path: str) -> dict[str, Any]:
    """Relit un rapport de simulation déjà enregistré.
            PARAMS: - path - STR: chemin du rapport, sous rapports_batailles/ (ex. rapports_batailles/changping.md)
            RETURN: contenu du rapport ou raison du refus"""
    return safe_read(path)
