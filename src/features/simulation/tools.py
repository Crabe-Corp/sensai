import json
from collections.abc import Callable
from typing import Any

from src.features.sec.permissions import safe_read, safe_write
from src.features.tools.registry import ToolRegistry, tool
from .commanders import pick_strategies
from .human_verif import confirm_simple, review_changes
from .kingdom_fight import resolve_battle
from .report import build_report
from .store import Simulation
from .strategies import STRATEGIES, catalog
from .grounding import check_narration

simulation_registry = ToolRegistry()
_sim: Simulation | None = None
NO_SIM = {"error": "No active simulation. The user must type /simulation."}
MAX_PASSAGES_CHARS = 3000

_client: Any = None
_get_model: Callable[[], str] = lambda: ""
_host = "http://localhost:11434"

def configure(client: Any, get_model: Callable[[], str], host: str) -> None:
    """Give the simulation access to the LLM client, the current model name and the Ollama host."""
    global _client, _get_model, _host
    _client, _get_model, _host = client, get_model, host

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

def kingdom_names() -> list[str]:
    return _sim.names() if _sim else []

@tool(registry=simulation_registry)
def list_kingdoms() -> dict[str, Any]:
    """List the current state of every kingdom in the simulation (troops, morale, gold, status).
            PARAMS: None
            RETURN: dictionary containing the list of kingdoms"""
    return {"kingdoms": _sim.kingdoms()} if _sim else NO_SIM

@tool(registry=simulation_registry)
def get_kingdom_state(kingdom: str) -> dict[str, Any]:
    """Give the state of one kingdom and its best active general.
            PARAMS: - kingdom - STR: name of the kingdom
            RETURN: dictionary with the statistics and the general, or an error"""
    if not _sim:
        return NO_SIM
    k = _sim.get_kingdom(kingdom)
    if not k:
        return {"error": f"Unknown kingdom. Available: {_sim.names()}"}
    return {**k, "best_general": _sim.best_general(k["id"])}

@tool(registry=simulation_registry)
def consult_art_of_war(situation: str) -> dict[str, Any]:
    """Look up Sun Tzu's Art of War when the user asks about strategies, what a strategy means, or what Sun Tzu would advise.
            PARAMS: - situation - STR: short description of the question or situation, written in English
            RETURN: the strategies of the simulation (with what each one thwarts) and passages from the sources"""
    passages = ""
    try:
        from src.RAG.retriever import retrieve_rag_context
        kwargs = {"ollama_url": _host, "ollama_model": _get_model()} if _client is not None else {}
        passages = (retrieve_rag_context(f"Sun Tzu Art of War strategy: {situation}", top_k=3, **kwargs) or "")[:MAX_PASSAGES_CHARS]
    except Exception:
        passages = ""
    return {"strategies": catalog(),
            "passages": passages or "No passage retrieved (RAG unavailable): rely on the strategies list.",
            "instruction": "Answer from the strategies list and the passages. Never use numbers found in the passages."}

@tool(registry=simulation_registry)
def simulate_battle(attacker: str, defender: str) -> dict[str, Any]:
    """Run a battle between two kingdoms. Call it immediately as soon as the user mentions an attack, a fight, a battle or a war. The commanders of both kingdoms choose their own strategies.
            PARAMS: - attacker - STR: name of the attacking kingdom
                    - defender - STR: name of the defending kingdom
            RETURN: battle summary (strategies, winner, losses, fallen general) or status rejected"""
    if not _sim:
        return NO_SIM
    a, b = _sim.get_kingdom(attacker), _sim.get_kingdom(defender)
    if not a or not b:
        return {"error": f"Unknown kingdom. Available: {_sim.names()}"}
    if a["id"] == b["id"]:
        return {"error": "A kingdom cannot fight itself."}
    if "annexed" in (a["status"], b["status"]):
        return {"error": "One of the kingdoms is already annexed."}

    gen_a, gen_b = _sim.best_general(a["id"]), _sim.best_general(b["id"])
    print("\nThe commanders are choosing the best strategies...")
    sa_key, sb_key, notes = pick_strategies(_client, _get_model(), _host, a, gen_a, b, gen_b,
                                            seed=_sim.seed + _sim.turn + 7919)
    changes, summary = resolve_battle(a, gen_a, b, gen_b, seed=_sim.seed + _sim.turn,
                                      strategy_a=sa_key, strategy_b=sb_key)
    summary["commanders"] = notes

    title = (f"{a['name']} [{STRATEGIES[sa_key].name}] attacks {b['name']} [{STRATEGIES[sb_key].name}] "
             f"({summary['winner']} wins)\n  {summary['matchup']}\n"
             f"  {a['name']} ({notes['attacker_choice']}): {notes['attacker_reason']}\n"
             f"  {b['name']} ({notes['defender_choice']}): {notes['defender_reason']}")
    accepted = review_changes(title, changes)
    if not accepted:
        return {
            "status": "rejected", 
            "facts": "The War Master has forbidden this clash. The armies hold their ground and no blood is shed."
        }
    _sim.apply(accepted, battle=summary)
    _sim.turn += 1

    losses = ", ".join(f"{k} {v:,}" for k, v in summary["casualties"].items())
    fell = f"General {summary['general_fallen']} fell." if summary["general_fallen"] else "No general fell."
    facts = (f"{summary['matchup']} {summary['winner']} beat {summary['loser']}. Losses: {losses}. {fell} "
             f"{len(accepted)} change(s) applied out of {len(changes)}.")
    return {"status": "applied", "applied": len(accepted), "rejected": len(changes) - len(accepted), "facts": facts}

@tool(registry=simulation_registry)
def get_simulation_facts() -> dict[str, Any]:
    """Get the figures of the simulation so far (battles with their strategies, fallen generals, final state).
            PARAMS: None
            RETURN: dictionary of facts taken from the simulation log"""
    return _sim.facts() if _sim else NO_SIM

@tool(registry=simulation_registry)
def write_battle_report(path: str, analysis: str) -> dict[str, Any]:
    """Write the end-of-simulation report in the allowed folder. The figures and the strategies used are added automatically.
            PARAMS: - path - STR: report path, under battle_reports/ (e.g. battle_reports/changping.md)
                    - analysis - STR: tactical analysis in markdown, based only on get_simulation_facts, without numbers
            RETURN: write status or the reason for the refusal"""
    if not _sim:
        return NO_SIM
    facts = _sim.facts()
    if facts["turns"] == 0:
        return {"status": "error", "reason": "No battle has taken place: run simulate_battle first."}
    problems = check_narration(analysis, [facts], _sim.names())
    if problems:
        return {"status": "error", "reason": "Analysis rejected: " + "; ".join(problems)
                + ". Rewrite it using only what get_simulation_facts returned, or copy the facts."}
    content = build_report(facts, analysis)

    def confirm(exists: bool) -> bool:
        preview = content if len(content) <= 2500 else content[:2500] + "\n[... preview truncated, the full report will be saved ...]"
        print(f"\n[REPORT PREVIEW → {path}]\n{preview}")
        return confirm_simple(f"Overwrite {path}?" if exists else f"Save {path}?")

    return safe_write(path, content, confirm=confirm)

@tool(registry=simulation_registry)
def read_battle_report(path: str) -> dict[str, Any]:
    """Read a simulation report that was already saved.
            PARAMS: - path - STR: report path, under battle_reports/ (e.g. battle_reports/changping.md)
            RETURN: content of the report or the reason for the refusal"""
    return safe_read(path)
