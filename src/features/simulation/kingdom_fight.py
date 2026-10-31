import random

from .human_verif import Change
from .strategies import DEFAULT_STRATEGY, STRATEGIES, describe_matchup, strength_multiplier

UPKEEP = 4.0
CAMPAIGN_COST = 1.5
ANNEX_THRESHOLD = 30_000

def _clamp(v: int) -> int:
    return max(0, min(100, v))

def _strength(k: dict, skill: int, multiplier: float = 1.0) -> float:
    morale_f = 0.5 + k["morale"] / 200
    supply = min(1.0, k["gold"] / max(1, k["troops"] * UPKEEP))
    supply_f = 0.7 + 0.3 * supply
    skill_f = 0.8 + skill / 250
    return k["troops"] * morale_f * supply_f * skill_f * multiplier

def win_probability(a: dict, skill_a: int, b: dict, skill_b: int, mult_a: float = 1.0, mult_b: float = 1.0) -> float:
    sa, sb = _strength(a, skill_a, mult_a) ** 2, _strength(b, skill_b, mult_b) ** 2
    return sa / (sa + sb)

def resolve_battle(a, gen_a, b, gen_b, seed: int,
                   strategy_a: str = DEFAULT_STRATEGY, strategy_b: str = DEFAULT_STRATEGY) -> tuple[list[Change], dict]:
    """Compute the outcome of a battle. Modifies NOTHING: returns a change set and a summary."""
    rng = random.Random(seed)
    sk_a = gen_a["tactical_skill"] if gen_a else 50
    sk_b = gen_b["tactical_skill"] if gen_b else 50
    mult_a = strength_multiplier(strategy_a, strategy_b)
    mult_b = strength_multiplier(strategy_b, strategy_a)
    p_a = win_probability(a, sk_a, b, sk_b, mult_a, mult_b)
    a_wins = rng.random() < p_a
    win, lose = (a, b) if a_wins else (b, a)
    win_strat, lose_strat = ((STRATEGIES[strategy_a], STRATEGIES[strategy_b]) if a_wins
                             else (STRATEGIES[strategy_b], STRATEGIES[strategy_a]))
    g_lose = gen_b if a_wins else gen_a

    u_lose = rng.uniform(0.25, 0.40)
    u_win = rng.uniform(0.08, 0.15)
    loss_lose = min(lose["troops"], int(lose["troops"] * u_lose * lose_strat.losses_mult))
    loss_win = min(win["troops"], int(win["troops"] * u_win * win_strat.losses_mult))
    general_fell = bool(g_lose) and rng.random() < 0.35
    lose_after = lose["troops"] - loss_lose
    reason = f"battle {a['name']} vs {b['name']}"

    changes = [
        Change("sim_kingdoms", win["id"], "troops", win["troops"], win["troops"] - loss_win, reason),
        Change("sim_kingdoms", lose["id"], "troops", lose["troops"], lose_after, reason),
        Change("sim_kingdoms", win["id"], "morale", win["morale"], _clamp(win["morale"] + 5), "victory"),
        Change("sim_kingdoms", lose["id"], "morale", lose["morale"],
               _clamp(lose["morale"] - 10 - (15 if general_fell else 0)),
               "defeat" + (" + general fallen" if general_fell else "")),
        Change("sim_kingdoms", win["id"], "gold", win["gold"],
               win["gold"] - min(win["gold"], int(win["troops"] * (CAMPAIGN_COST + win_strat.gold_cost))), "campaign cost"),
        Change("sim_kingdoms", lose["id"], "gold", lose["gold"],
               lose["gold"] - min(lose["gold"], int(lose["troops"] * (CAMPAIGN_COST + lose_strat.gold_cost))), "campaign cost"),
    ]
    if general_fell:
        changes.append(Change("sim_generals", g_lose["name"], "status", "active", "fallen", "killed in action"))
    if lose_after < ANNEX_THRESHOLD:
        changes.append(Change("sim_kingdoms", lose["id"], "status", "independent", "annexed", "army annihilated"))

    summary = {"attacker": a["name"], "defender": b["name"],
               "attacker_strategy": strategy_a, "defender_strategy": strategy_b,
               "matchup": describe_matchup(a["name"], strategy_a, b["name"], strategy_b),
               "winner": win["name"], "loser": lose["name"], "p_attacker": round(p_a, 3),
               "casualties": {win["name"]: loss_win, lose["name"]: loss_lose},
               "general_fallen": g_lose["name"] if general_fell else None}
    return changes, summary
