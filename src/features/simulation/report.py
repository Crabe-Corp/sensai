def build_report(facts: dict, analysis: str) -> str:
    """Assemble le rapport : bilan chiffré (issu de la base) puis analyse tactique (rédigée par le LLM)."""
    out = [f"# Rapport de simulation (seed {facts['seed']})", "", f"Tours joués : {facts['turns']}", "", "## Batailles"]
    for i, b in enumerate(facts["battles"], 1):
        pertes = ", ".join(f"{k} {v:,}" for k, v in b["casualties"].items())
        fell = f", général tombé : {b['general_fallen']}" if b["general_fallen"] else ""
        out.append(f"{i}. {b['winner']} bat {b['loser']} (probabilité attaquant {b['p_attacker']:.0%}), pertes : {pertes}{fell}")
    out += ["", "## Généraux tombés"]
    out += [f"- {g['name']} ({g['kingdom_id']})" for g in facts["fallen"]] or ["- Aucun"]
    out += ["", "## État final", "| Royaume | Troupes | Moral | Or | Statut |", "|---|---|---|---|---|"]
    out += [f"| {k['name']} | {k['troops']:,} | {k['morale']} | {k['gold']:,} | {k['status']} |" for k in facts["kingdoms"]]
        out += ["", "## Analyse tactique", "",
            "> Section rédigée par le modèle de langage. Seuls les chiffres des sections précédentes proviennent de la base.",
            "", analysis.strip(), ""]
    return "\n".join(out)
