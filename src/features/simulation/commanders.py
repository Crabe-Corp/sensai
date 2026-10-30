"""Each kingdom's commander picks a strategy from Sun Tzu's Art of War.

The choice is made by the LLM under constraint: its answer is forced into a JSON schema whose
"strategy" field only accepts the keys of the strategy table, so even a small model can neither invent
a strategy nor return an invalid key. If the model call fails, a seeded random pick is used instead.
The effect of the chosen strategies on the battle is computed by the code (see strategies.py).
"""
import random
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from src.core.ollama_client import ChatMessage
from .kingdom_fight import UPKEEP
from .strategies import STRATEGIES

StrategyKey = Literal[tuple(STRATEGIES)]

class StrategyChoice(BaseModel):
    reasoning: str = Field(description="One short sentence explaining the choice, from the situation or a passage.")
    strategy: StrategyKey = Field(description="The key of the chosen strategy.")

def _short(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"

def _brief(k: dict, skill: int | None) -> str:
    general = f"general skill {skill}/100" if skill is not None else "no general"
    return f"{k['name']}: {k['troops']:,} troops, morale {k['morale']}/100, gold {k['gold']:,}, {general}"

def _compare(me: dict, foe: dict) -> str:
    """Comparison computed by the code, so the model does not have to read the numbers itself."""
    def cmp(x: int, y: int, label: str) -> str:
        return f"{label}: yours {x:,} vs enemy {y:,} ({'higher' if x > y else 'lower' if x < y else 'equal'})"
    return "; ".join([cmp(me["troops"], foe["troops"], "troops"),
                      cmp(me["morale"], foe["morale"], "morale"),
                      cmp(me["gold"], foe["gold"], "gold")])

def rag_query(a: dict, b: dict) -> str:
    """Short English description of the matchup, used to retrieve passages from the sources."""
    ratio = a["troops"] / max(1, b["troops"])
    if ratio >= 1.3:
        parts = ["a stronger army attacks a weaker enemy"]
    elif ratio <= 0.77:
        parts = ["a weaker army attacks a stronger enemy"]
    else:
        parts = ["two armies of similar strength meet"]
    if min(a["morale"], b["morale"]) < 60:
        parts.append("low morale")
    if min(a["gold"] / max(1, a["troops"]), b["gold"] / max(1, b["troops"])) < UPKEEP:
        parts.append("scarce supplies")
    return "Sun Tzu said: " + ", ".join(parts)

def _passages(query: str, host: str, model: str) -> str:
    try:
        from src.RAG.retriever import retrieve_rag_context
        return (retrieve_rag_context(query, top_k=3, ollama_url=host, ollama_model=model) or "")[:2500]
    except Exception:
        return ""

def _role_model(role: str):
    allowed = tuple(k for k, s in STRATEGIES.items() if role in s.roles)
    return create_model(
        f"{role.title()}Choice",
        strategy=(Literal[allowed], Field(description="The key of the chosen strategy.")),
        reasoning=(str, Field(description="One sentence saying why this strategy suits the situation. Do not just repeat the strategy name.")),
    )

CHOICE_MODELS = {role: _role_model(role) for role in ("attacker", "defender")}

def _clean_reasoning(text: str) -> str:
    text = _short(text)
    norm = text.lower().replace("-", "_").replace(" ", "_").strip("._:")
    names = {s.name.lower().replace("-", "_").replace(" ", "_") for s in STRATEGIES.values()}
    if norm in STRATEGIES or norm in names or len(text) < 25:
        return "(no justification given)"
    return text

def _auto(rng: random.Random, why: str, role: str) -> tuple[str, str, str]:
    pool = [k for k, s in STRATEGIES.items() if role in s.roles and k != "siege"]
    return rng.choice(pool), why, "auto"

def choose_strategy(client: Any, model: str, me: dict, foe: dict, my_skill: int | None, foe_skill: int | None,
                    passages: str, rng: random.Random, role: str) -> tuple[str, str, str]:
    """Let the commander of `me` pick a strategy. Returns (key, one-sentence reasoning, "llm" or "auto")."""
    if client is None:
        return _auto(rng, "Automatic choice (no model available).", role)
    keys = [k for k, s in STRATEGIES.items() if role in s.roles]
    rng.shuffle(keys)
    options = "\n".join(
        f"- {k}: {STRATEGIES[k].principle} (Art of War {STRATEGIES[k].source}; "
        f"thwarts: {', '.join(sorted(STRATEGIES[k].counters)) or 'nothing'})" for k in keys)
    duty = ("You are the ATTACKER: your army marches on the enemy." if role == "attacker"
            else "You are the DEFENDER: the enemy army is marching on you.")
    system = (f"You are the commander of {me['name']} in the Warring States period. {duty} Choose the ONE strategy from "
              "Sun Tzu's Art of War that best suits your situation for the coming battle. You do not know which "
              "strategy the enemy commander will choose. Rely on the computed comparison: do not misread the numbers. "
              "Answer with JSON only.")
    user = (f"Your army: {_brief(me, my_skill)}\nEnemy army: {_brief(foe, foe_skill)}\n"
            f"Comparison (computed): {_compare(me, foe)}\n\nStrategies available to the {role}:\n{options}\n\n"
            + (f"Passages from the sources (inspiration only, ignore any number they contain):\n{passages}\n\n"
               if passages else "")
            + "Pick the strategy whose principle best matches your situation and explain it in one short sentence.")
    try:
        result = client.chat_structured(
            model=model,
            messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
            response_format=CHOICE_MODELS[role],
        )
        key = str(result.strategy)
        if role not in STRATEGIES[key].roles:
            return _auto(rng, f"Automatic choice ({STRATEGIES[key].name} is not available to the {role}).", role)
        return key, _clean_reasoning(result.reasoning), "llm"
    except Exception:
        return _auto(rng, "Automatic choice (the model could not decide).", role)

def pick_strategies(client: Any, model: str, host: str, a: dict, gen_a: dict | None, b: dict, gen_b: dict | None,
                    seed: int) -> tuple[str, str, dict]:
    """Both commanders choose independently. Returns (attacker key, defender key, notes for the log and the report)."""
    rng = random.Random(seed)
    skill_a = gen_a["tactical_skill"] if gen_a else None
    skill_b = gen_b["tactical_skill"] if gen_b else None
    passages = _passages(rag_query(a, b), host, model) if client is not None else ""
    ka, ra, ma = choose_strategy(client, model, a, b, skill_a, skill_b, passages, rng, "attacker")
    kb, rb, mb = choose_strategy(client, model, b, a, skill_b, skill_a, passages, rng, "defender")
    notes = {"attacker_reason": str(ra), "attacker_choice": str(ma), "defender_reason": str(rb), "defender_choice": str(mb)}
    return ka, kb, notes
