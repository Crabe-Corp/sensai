def build_report(facts: dict, analysis: str) -> str:
    """Assemble the report: figures and strategies (from the database), then the tactical analysis (written by the LLM)."""
    out = [f"# Simulation report (seed {facts['seed']})", "", f"Battles played: {facts['turns']}", "", "## Battle"]
    for i, b in enumerate(facts["battles"], 1):
        losses = ", ".join(f"{k} {v:,}" for k, v in b["casualties"].items())
        fell = f", general fallen: {b['general_fallen']}" if b["general_fallen"] else ""
        out.append(f"{i}. {b['winner']} beat {b['loser']} (attacker win probability {b['p_attacker']:.0%}), losses: {losses}{fell}")
        if b.get("matchup"):
            out.append(f"   - Strategies: {b['matchup']}")
        c = b.get("commanders")
        if c:
            out.append(f"   - Commanders' reasoning (written by the model, choice made by '{c['attacker_choice']}' / '{c['defender_choice']}'): "
                       f"{b['attacker']}: {c['attacker_reason']} | {b['defender']}: {c['defender_reason']}")
    out += ["", "## Fallen generals"]
    out += [f"- {g['name']} ({g['kingdom_id']})" for g in facts["fallen"]] or ["- None"]
    out += ["", "## Final state", "| Kingdom | Troops | Morale | Gold | Status |", "|---|---|---|---|---|"]
    out += [f"| {k['name']} | {k['troops']:,} | {k['morale']} | {k['gold']:,} | {k['status']} |" for k in facts["kingdoms"]]
    out += ["", "## Tactical analysis", "",
            "Section written by the language model:",
            "", analysis.strip(), ""]
    return "\n".join(out)
