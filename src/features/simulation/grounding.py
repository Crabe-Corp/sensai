"""Deterministic check of the model's narration against the tool results of the same turn.

It cannot prove that a text is true. It catches the most damaging kinds of hallucination: figures that no
tool returned, kingdoms that took no part in the battle, claims about a report nobody wrote, and claims that
a strategy countered another when the code says otherwise. When a check fails, the code-written "facts"
sentence is shown instead of the model's text (fail closed).
"""
import json
import re

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CLAIM = re.compile(r"\b(counter\w*|thwart\w*|outmaneuver\w*|outmanoeuvr\w*)", re.IGNORECASE)
_NEITHER = re.compile(r"neither strategy thwarts the other", re.IGNORECASE)

def _figures(text: str) -> set[str]:
    out = set()
    for m in _NUMBER.finditer(text):
        n = m.group().replace(",", "")
        if len(n) > 1 or "." in n:
            out.add(n)
    return out

def check_narration(reply: str, tool_results: list[dict], known_names: list[str]) -> list[str]:
    """Problems found in the model's text compared with the tool results (empty list = grounded)."""
    trusted = [{k: v for k, v in r.items() if k != "passages"} for r in tool_results]
    source = json.dumps(trusted, ensure_ascii=False, default=str)
    low_source = source.lower()
    problems: list[str] = []

    unknown = sorted(_figures(reply) - _figures(source))
    if unknown:
        problems.append("figures that no tool returned: " + ", ".join(unknown))
    for name in known_names:
        pattern = rf"\b{re.escape(name)}\b"
        if re.search(pattern, reply) and not re.search(pattern, source):
            problems.append(f"{name} took no part in the tool results")
    counter_ok = bool(re.search(r"\bthwarts (?!the other)", source))
    if _CLAIM.search(_NEITHER.sub("", reply)) and not counter_ok:
        problems.append("claims that a strategy countered another, which the tool results do not say")
    wrote_or_read = any(isinstance(r.get("path"), str) or isinstance(r.get("content"), str) for r in trusted)
    if "battle_reports/" in reply and not wrote_or_read:
        problems.append("mentions a report file that no tool wrote")
    return problems

def settle_reply(reply: str, tool_results: list[dict], known_names: list[str]) -> tuple[str, list[str]]:
    """What to show and store after a simulation turn: the model's text if grounded, else the code's own facts."""
    if not tool_results:
        return "", ["No tool was called: the answer was not based on the simulation and was discarded."]
    facts = " ".join(r["facts"] for r in tool_results if isinstance(r.get("facts"), str))
    fallback = facts or json.dumps(tool_results[-1], ensure_ascii=False, default=str)[:600]
    if not reply.strip():
        return fallback, []
    problems = check_narration(reply, tool_results, known_names)
    return (fallback, problems) if problems else (reply, [])
