"""Strategies taken from Sun Tzu's Art of War (Lionel Giles' translation, the file indexed by the RAG).

All effects are game-balance values, not historical facts. The "thwarts" relation is a game-design
reading of the cited passages, not a sentence of the book. All numbers live here: the LLM only
picks a strategy key, the code applies the effect.
"""

from dataclasses import dataclass

COUNTER_BONUS = 1.12
COUNTER_MALUS = 0.92
DEFAULT_STRATEGY = "direct_attack"

@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    source: str
    principle: str
    counters: frozenset[str]
    roles: frozenset[str] = frozenset({"attacker", "defender"})
    gold_cost: float = 0.0
    strength_mult: float = 1.0
    losses_mult: float = 1.0

ATTACKER, DEFENDER = frozenset({"attacker"}), frozenset({"defender"})

STRATEGIES: dict[str, Strategy] = {s.key: s for s in (
    Strategy("direct_attack", "Direct attack", "V.5",
             "Meet the enemy head-on: the direct method joins battle but rarely wins it alone.",
             frozenset(), roles=ATTACKER),
    Strategy("deception", "Deception", "I.18-22",
             "All warfare is based on deception: feign weakness, hold out baits, strike where the enemy is unprepared.",
             frozenset({"direct_attack", "siege"})),
    Strategy("prepared_defense", "Prepared defense", "IV.1-7, VIII.11",
             "Put yourself beyond the possibility of defeat first, and rely on your own readiness to receive the enemy.",
             frozenset({"deception", "lightning_war"}), roles=DEFENDER),
    Strategy("indirect_maneuver", "Indirect maneuver", "V.5, VI.11, VI.30",
             "Avoid what is strong and strike at what is weak; attack elsewhere to force the enemy to move.",
             frozenset({"prepared_defense", "direct_attack"})),
    Strategy("spies", "Spies", "XIII",
             "Foreknowledge of the enemy can only come from other men; do not grudge the silver spent on spies.",
             frozenset({"deception", "indirect_maneuver"}), gold_cost=0.3),
    Strategy("lightning_war", "Lightning war", "II.5-6, XI.19",
             "Rapidity is the essence of war; no country has ever benefited from a prolonged campaign.",
             frozenset({"spies", "siege"}), roles=ATTACKER),
    Strategy("siege", "Siege of walled cities", "III.3-5",
             "The worst policy of all: months are wasted and a third of the men can fall while the town stays untaken.",
             frozenset(), roles=ATTACKER, strength_mult=0.90, losses_mult=1.30),
)}

def resolve_key(raw: object) -> str | None:
    """Turn what the LLM passed (a key or a strategy name, any case) into a valid key, or None."""
    if not isinstance(raw, str):
        return None
    norm = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if norm in STRATEGIES:
        return norm
    for s in STRATEGIES.values():
        if s.name.lower().replace("-", "_").replace(" ", "_") == norm:
            return s.key
    return None

def strength_multiplier(mine: str, theirs: str) -> float:
    """Strength multiplier of the side using `mine` against `theirs`."""
    s = STRATEGIES[mine]
    m = s.strength_mult
    if theirs in s.counters:
        m *= COUNTER_BONUS
    elif mine in STRATEGIES[theirs].counters:
        m *= COUNTER_MALUS
    return m

def describe_matchup(name_a: str, key_a: str, name_b: str, key_b: str) -> str:
    """One sentence stating who used what and who thwarted whom. Built by the code, never by the LLM."""
    sa, sb = STRATEGIES[key_a], STRATEGIES[key_b]
    text = f"{name_a} used {sa.name} (Art of War {sa.source}); {name_b} used {sb.name} (Art of War {sb.source})."
    if key_b in sa.counters:
        text += f" {sa.name} thwarts {sb.name}: advantage {name_a}."
    elif key_a in sb.counters:
        text += f" {sb.name} thwarts {sa.name}: advantage {name_b}."
    else:
        text += " Neither strategy thwarts the other."
    for name, s in ((name_a, sa), (name_b, sb)):
        if s.strength_mult < 1.0:
            text += f" {name}'s choice is a poor policy according to the Art of War and weakens its army."
    return text

def catalog() -> list[dict]:
    """The strategies shown to the LLM when the user asks about Sun Tzu's strategies."""
    return [{"key": s.key, "name": s.name, "roles": sorted(s.roles), "source": f"Art of War {s.source}", "principle": s.principle,
             "thwarts": sorted(s.counters), "costs_extra_gold": s.gold_cost > 0} for s in STRATEGIES.values()]
