from dataclasses import dataclass

@dataclass(frozen=True)
class Change:
    table: str
    key: str
    field: str
    old: object
    new: object
    reason: str = ""

    def render(self) -> str:
        return f"{self.table}[{self.key}].{self.field}: {self.old} → {self.new}  ({self.reason})"

def confirm_simple(question: str) -> bool:
    while True:
        try:
            ans = input(f"{question} [O/N] > ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            return False
        if ans in ("O", "N"):
            return ans == "O"


def review_changes(title: str, changes: list[Change]) -> list[Change]:
    """Affiche le diff et renvoie les changements acceptés (liste vide = refus total)."""
    print(f"\n[VALIDATION REQUISE] {title}")
    for i, c in enumerate(changes, 1):
        print(f"  {i:>2}. {c.render()}")
    while True:
        try:
            choice = input("[T]out appliquer / [N]on / [S]électionner > ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            return []
        if choice == "T":
            return changes
        if choice == "N":
            return []
        if choice == "S":
            try:
                raw = input("Numéros à appliquer (ex: 1,3) > ")
            except (KeyboardInterrupt, EOFError):
                return []
            idx = {int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}
            return [c for i, c in enumerate(changes, 1) if i in idx]
