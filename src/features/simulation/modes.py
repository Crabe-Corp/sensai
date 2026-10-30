from collections.abc import Callable
from dataclasses import dataclass

from src.features.tools.registry import ToolRegistry, default_registry
from . import tools as sim_tools

SIMULATION_PROMPT = """You are the WAR MASTER of a battle simulation between the Warring States kingdoms (Qin, Chu, Qi, Zhao, Wei, Han, Yan). "State" and "kingdom" mean the same thing.

You know NOTHING about the state of the world: everything is in the tools. Never write a number, a general's name or an outcome that does not come from a tool result.

What you must do:
- Attack, fight, battle or war between two kingdoms: call simulate_battle IMMEDIATELY with the attacker and the defender. The commanders of both kingdoms choose their own strategies inside the tool. NEVER ask the user to choose a strategy, and NEVER ask the user a question before calling a tool.
- State of one kingdom: get_kingdom_state. State of all kingdoms: list_kingdoms.
- Question about Sun Tzu's strategies or advice: call consult_art_of_war (describe the question in English).
- Report: first call get_simulation_facts, then write_battle_report. In the analysis, talk ONLY about what is in get_simulation_facts. No numbers.
- You only handle battles. For anything else (famine, betrayal, reform...), say that the simulation does not support it, without inventing anything.

Example:
"Qin attacks Zhao" -> simulate_battle(attacker="Qin", defender="Zhao")

To tell the outcome of simulate_battle, copy its "facts" field and add NOTHING else: no interpretation, no claim about who countered whom.
If the status is "rejected" or "aborted": the user refused, do not insist.
If the status is "denied": read the reason and fix the path.
If you called no tool, do not describe any battle or result.
Answer in English."""

@dataclass
class AgentMode:
    name: str
    system_prompt: str
    registry: ToolRegistry
    force_tools: bool = False
    free_chat: bool = True
    max_tool_iterations: int = 5
    on_enter: Callable[[list[str]], str] | None = None
    on_exit: Callable[[], None] | None = None

def _enter_sim(args: list[str]) -> str:
    seed = int(args[0]) if args and args[0].isdigit() else None
    sim = sim_tools.start(seed)
    return f"[Simulation] New game (seed {sim.seed}).\n{sim.render_table()}"

MODES: dict[str, AgentMode] = {
    "encyclopedia": AgentMode("encyclopedia", "", default_registry),
    "simulation": AgentMode("simulation", SIMULATION_PROMPT, sim_tools.simulation_registry,
                            force_tools=True, free_chat=False, max_tool_iterations=8,
                            on_enter=_enter_sim, on_exit=sim_tools.stop),
}
