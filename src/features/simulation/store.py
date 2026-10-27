import json
import random
import sqlite3
from pathlib import Path

from src.features.sec.permissions import PROJECT_ROOT
from .human_verif import Change
from .seed import GENERALS, KINGDOMS

DB_PATH = PROJECT_ROOT / "simulation.db"

WHITELIST = {
    "sim_kingdoms": ("id", {"troops": (0, 2_000_000), "morale": (0, 100),
                            "gold": (0, 20_000_000), "status": {"independent", "annexed"}}),
    "sim_generals": ("name", {"status": {"active", "fallen", "exiled"}, "tactical_skill": (0, 100)}),
}

DDL = """
DROP TABLE IF EXISTS sim_kingdoms; DROP TABLE IF EXISTS sim_generals; DROP TABLE IF EXISTS sim_log;
CREATE TABLE sim_kingdoms (id TEXT PRIMARY KEY, name TEXT NOT NULL, troops INTEGER NOT NULL,
                           morale INTEGER NOT NULL, gold INTEGER NOT NULL, status TEXT NOT NULL);
CREATE TABLE sim_generals (name TEXT PRIMARY KEY, kingdom_id TEXT NOT NULL,
                           tactical_skill INTEGER NOT NULL, status TEXT NOT NULL);
CREATE TABLE sim_log (id INTEGER PRIMARY KEY AUTOINCREMENT, turn INTEGER, kind TEXT, detail TEXT);
"""

def validate(c: Change) -> str | None:
    spec = WHITELIST.get(c.table)
    if not spec:
        return f"table not allowed: {c.table}"
    rule = spec[1].get(c.field)
    if rule is None:
        return f"field not allowed: {c.field}"
    if isinstance(rule, tuple):
        if not isinstance(c.new, int) or isinstance(c.new, bool) or not rule[0] <= c.new <= rule[1]:
            return f"{c.field} must be an integer within {rule}, got {c.new!r}"
    elif c.new not in rule:
        return f"{c.field} must be one of {sorted(rule)}, got {c.new!r}"
    return None

class Simulation:
    def __init__(self, seed: int | None = None, db_path: Path = DB_PATH) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        self.turn = 0
        self._create()

    def _create(self) -> None:
        """Draw the initial state around the values of seed.py. Same seed = same starting state."""
        rng = random.Random(self.seed)
        clamp = lambda v: max(0, min(100, v))
        self.conn.executescript(DDL)
        with self.conn:
            for kid, name, troops, morale, gold in KINGDOMS:
                self.conn.execute("INSERT INTO sim_kingdoms VALUES (?,?,?,?,?,?)", (
                    kid, name, int(troops * rng.uniform(0.85, 1.15)),
                    clamp(morale + rng.randint(-8, 8)), int(gold * rng.uniform(0.8, 1.2)), "independent"))
            for name, kid, skill, status in GENERALS:
                self.conn.execute("INSERT INTO sim_generals VALUES (?,?,?,?)",
                                  (name, kid, clamp(skill + rng.randint(-5, 5)), status))

    def get_kingdom(self, ident: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM sim_kingdoms WHERE LOWER(id)=LOWER(?) OR LOWER(name)=LOWER(?)",
                                (ident.strip(), ident.strip())).fetchone()
        return dict(row) if row else None

    def best_general(self, kingdom_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM sim_generals WHERE kingdom_id=? AND status='active' "
                                "ORDER BY tactical_skill DESC LIMIT 1", (kingdom_id,)).fetchone()
        return dict(row) if row else None

    def names(self) -> list[str]:
        return [r["name"] for r in self.conn.execute("SELECT name FROM sim_kingdoms")]

    def kingdoms(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM sim_kingdoms ORDER BY troops DESC")]

    def log(self, kind: str, detail: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO sim_log(turn, kind, detail) VALUES (?,?,?)", (self.turn, kind, detail))

    def apply(self, changes: list[Change]) -> int:
        for c in changes:
            if (err := validate(c)):
                raise ValueError(err)
        with self.conn:
            for c in changes:
                key_col, _ = WHITELIST[c.table]
                self.conn.execute(f"UPDATE {c.table} SET {c.field} = ? WHERE {key_col} = ?", (c.new, c.key))
                self.conn.execute("INSERT INTO sim_log(turn, kind, detail) VALUES (?, 'change', ?)",
                                  (self.turn, c.render()))
        return len(changes)

    def facts(self) -> dict:
        battles = [json.loads(r["detail"]) for r in
                   self.conn.execute("SELECT detail FROM sim_log WHERE kind='battle' ORDER BY id")]
        fallen = [dict(r) for r in self.conn.execute("SELECT name, kingdom_id FROM sim_generals WHERE status='fallen'")]
        return {"seed": self.seed, "turns": self.turn, "battles": battles,
                "fallen": fallen, "kingdoms": self.kingdoms()}

    def render_table(self) -> str:
        rows = [f"{'Kingdom':<8} {'Troops':>8} {'Morale':>6} {'Gold':>10}  Status"]
        rows += [f"{k['name']:<8} {k['troops']:>8,} {k['morale']:>6} {k['gold']:>10,}  {k['status']}"
                 for k in self.kingdoms()]
        return "\n".join(rows)

    def close(self) -> None:
        self.conn.close()
