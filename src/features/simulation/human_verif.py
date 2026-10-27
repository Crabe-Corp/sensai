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
            ans = input(f"{question} [Y/N] > ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            return False
        if ans in ("Y", "O"):
            return True
        if ans == "N":
            return False


def review_changes(title: str, changes: list[Change]) -> list[Change]:
    """Show the diff and return the accepted changes (empty list = full refusal)."""
    print(f"\n[APPROVAL REQUIRED] {title}")
    for i, c in enumerate(changes, 1):
        print(f"  {i:>2}. {c.render()}")
    while True:
        try:
            choice = input("[A]pply all / [N]o / [S]elect > ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            return []
        if choice in ("A"):
            return changes
        if choice == "N":
            return []
        if choice == "S":
            try:
                raw = input("Numbers to apply (e.g. 1,3) > ")
            except (KeyboardInterrupt, EOFError):
                return []
            idx = {int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}
            return [c for i, c in enumerate(changes, 1) if i in idx]
