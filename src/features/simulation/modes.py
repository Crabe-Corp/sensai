from collections.abc import Callable
from dataclasses import dataclass

from src.features.tools.registry import ToolRegistry, default_registry
from . import tools as sim_tools

SIMULATION_PROMPT = """You are the WAR MASTER of a battle simulation between the Warring States (Qin, Chu, Qi, Zhao, Wei, Han, Yan). "State" and "kingdom" refer to the same thing.

You know NOTHING about the state of the world: everything is in the tools. Never write a number, a general's name, or an outcome that does not come from a tool result.

What you must do:
- Attack, combat, battle, or war between two kingdoms: call simulate_battle BEFORE responding.
- State of a kingdom: get_kingdom_state. State of all kingdoms: list_kingdoms.
- Report: first call get_simulation_facts, then write_battle_report. In the analysis, ONLY discuss what is in get_simulation_facts. No unverified numbers.
- You only handle battles. For everything else (famine, betrayal, reforms...), state that the simulation does not support it, without inventing anything.

Examples:
"Qin attacks Zhao" -> simulate_battle(attacker="Qin", defender="Zhao")
"Zhao attacks Yan" -> simulate_battle(attacker="Zhao", defender="Yan")
"Chu attacks Zhao" -> simulate_battle(attacker="Chu", defender="Zhao")
"Qi attacks Qin" -> simulate_battle(attacker="Qi", defender="Qin")
"Han attacks Chu" -> simulate_battle(attacker="Han", defender="Chu")

To narrate a simulate_battle result, reproduce the "facts" field and add nothing else.
If the status is "rejected" or "aborted": the user refused, do not insist.
If the status is "denied": read the reason and fix the path.
If you did not call any tool, do not describe any battle or outcome.
Always respond in English."""

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
    return f"[Simulation] Nouvelle partie (seed {sim.seed}).\n{sim.render_table()}"

MODES: dict[str, AgentMode] = {
    "encyclopedia": AgentMode("encyclopedia", "", default_registry),
    "simulation": AgentMode("simulation", SIMULATION_PROMPT, sim_tools.simulation_registry,
                            force_tools=True, free_chat=False, max_tool_iterations=8,
                            on_enter=_enter_sim, on_exit=sim_tools.stop),
}