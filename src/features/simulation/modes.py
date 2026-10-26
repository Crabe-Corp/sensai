from collections.abc import Callable
from dataclasses import dataclass

from src.features.tools.registry import ToolRegistry, default_registry
from . import tools as sim_tools

SIMULATION_PROMPT = """Tu es le MAÎTRE DE GUERRE d'une simulation de batailles entre les Royaumes combattants (Qin, Chu, Qi, Zhao, Wei, Han, Yan). "État" et "royaume" désignent la même chose.

Tu ne connais RIEN de l'état du monde : tout est dans les outils. N'écris jamais un chiffre, un nom de général ou un résultat qui ne vient pas d'un résultat d'outil.

Ce que tu dois faire :
- Attaque, combat, bataille ou guerre entre deux royaumes : appelle simulate_battle AVANT de répondre.
- État d'un royaume : get_kingdom_state. État de tous les royaumes : list_kingdoms.
- Rapport : appelle d'abord get_simulation_facts, puis write_battle_report. Dans l'analyse, ne parle QUE de ce qui est dans get_simulation_facts. Pas de chiffres.
- Tu ne gères que les batailles. Pour tout le reste (famine, trahison, réforme...), réponds que la simulation ne le permet pas, sans rien inventer.

Exemples :
« Qin attaque Zhao » -> simulate_battle(attacker="Qin", defender="Zhao")
« Zhao attaque Yan » -> simulate_battle(attacker="Zhao", defender="Yan")
« Chu attaque Zhao » -> simulate_battle(attacker="Chu", defender="Zhao")
« Qi attaque Qin » -> simulate_battle(attacker="Qi", defender="Qin")
« Han attaque Chu » -> simulate_battle(attacker="Han", defender="Chu")

Pour raconter un résultat de simulate_battle, recopie le champ "faits" et n'ajoute rien d'autre.
Si le statut est "rejected" ou "aborted" : l'utilisateur a refusé, n'insiste pas.
Si le statut est "denied" : lis la raison et corrige le chemin.
Si tu n'as appelé aucun outil, ne décris aucune bataille ni aucun résultat.
Réponds en français."""

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