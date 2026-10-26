import random

from .human_verif import Change

UPKEEP = 4.0
CAMPAIGN_COST = 1.5
ANNEX_THRESHOLD = 30_000

def _clamp(v: int) -> int:
    return max(0, min(100, v))

def _strength(k: dict, skill: int) -> float:
    morale_f = 0.5 + k["morale"] / 200
    supply = min(1.0, k["gold"] / max(1, k["troops"] * UPKEEP))
    supply_f = 0.7 + 0.3 * supply
    skill_f = 0.8 + skill / 250
    return k["troops"] * morale_f * supply_f * skill_f

def win_probability(a: dict, skill_a: int, b: dict, skill_b: int) -> float:
    sa, sb = _strength(a, skill_a) ** 2, _strength(b, skill_b) ** 2
    return sa / (sa + sb)

def resolve_battle(a, gen_a, b, gen_b, seed: int) -> tuple[list[Change], dict]:
    """Calcule l'issue d'une bataille. Ne modifie RIEN : renvoie un ChangeSet et un résumé."""
    rng = random.Random(seed)
    sk_a = gen_a["tactical_skill"] if gen_a else 50
    sk_b = gen_b["tactical_skill"] if gen_b else 50
    p_a = win_probability(a, sk_a, b, sk_b)
    a_wins = rng.random() < p_a
    win, lose = (a, b) if a_wins else (b, a)
    g_lose = gen_b if a_wins else gen_a

    loss_lose = int(lose["troops"] * rng.uniform(0.25, 0.40))
    loss_win = int(win["troops"] * rng.uniform(0.08, 0.15))
    general_fell = bool(g_lose) and rng.random() < 0.35
    lose_after = lose["troops"] - loss_lose
    reason = f"bataille {a['name']} vs {b['name']}"

    changes = [
        Change("sim_kingdoms", win["id"], "troops", win["troops"], win["troops"] - loss_win, reason),
        Change("sim_kingdoms", lose["id"], "troops", lose["troops"], lose_after, reason),
        Change("sim_kingdoms", win["id"], "morale", win["morale"], _clamp(win["morale"] + 5), "victoire"),
        Change("sim_kingdoms", lose["id"], "morale", lose["morale"],
               _clamp(lose["morale"] - 10 - (15 if general_fell else 0)),
               "défaite" + (" + général tombé" if general_fell else "")),
        Change("sim_kingdoms", win["id"], "gold", win["gold"],
               win["gold"] - min(win["gold"], int(win["troops"] * CAMPAIGN_COST)), "coût de campagne"),
        Change("sim_kingdoms", lose["id"], "gold", lose["gold"],
               lose["gold"] - min(lose["gold"], int(lose["troops"] * CAMPAIGN_COST)), "coût de campagne"),
    ]
    if general_fell:
        changes.append(Change("sim_generals", g_lose["name"], "status", "active", "fallen", "mort au combat"))
    if lose_after < ANNEX_THRESHOLD:
        changes.append(Change("sim_kingdoms", lose["id"], "status", "independent", "annexed", "armée anéantie"))

    summary = {"winner": win["name"], "loser": lose["name"], "p_attacker": round(p_a, 3),
               "casualties": {win["name"]: loss_win, lose["name"]: loss_lose},
               "general_fallen": g_lose["name"] if general_fell else None}
    return changes, summary
