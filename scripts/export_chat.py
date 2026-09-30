#!/usr/bin/env python3
"""Export de conversation Open WebUI en Markdown"""

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("openwebui_data/webui.db")
EXPORTS_DIR = Path("exports")
IGNORED_COMMANDS = ("/persona", "/learn", "/export", "/clearcache", "/prompts", "/sessions")


def get_latest_chat(conn: sqlite3.Connection) -> tuple[str, str, int]:
    row = conn.execute(
        "SELECT title, chat, created_at FROM chat ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise ValueError("Aucune conversation trouvée dans la base.")
    return row[0] or "Session", row[1] or "{}", row[2] or 0


def extract_clean_messages(raw_chat: str) -> list[tuple[str, str]]:
    data = json.loads(raw_chat)
    raw_msgs = data.get("history", {}).get("messages", {})
    curr_id = data.get("history", {}).get("currentId")

    chain = []
    visited = set()
    while curr_id and curr_id in raw_msgs and curr_id not in visited:
        visited.add(curr_id)
        msg = raw_msgs[curr_id]
        chain.append((msg.get("role", "unknown"), msg.get("content", "").strip()))
        curr_id = msg.get("parentId")
    chain.reverse()

    return [
        (role, content) for role, content in chain
        if content and not any(content.lower().startswith(p) for p in IGNORED_COMMANDS)
    ]


def export_to_markdown(title: str, created_at: int, messages: list[tuple[str, str]], out_file: Path | None = None) -> Path:
    date_str = datetime.fromtimestamp(created_at).strftime("%d/%m/%Y à %H:%M") if created_at else ""
    lines = [
        f"# {title}",
        f"*Date de la session : {date_str}*\n",
        "---",
    ]

    roles = {"user": "Joueur", "assistant": "Chroniqueur"}
    for role, text in messages:
        lines.append(f"\n### {roles.get(role, role.capitalize())}\n\n{text}\n")

    lines.append("---\n*Exporté automatiquement par SensAI")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    target = out_file or (EXPORTS_DIR / f"{slug}.md")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main():
    if not DB_PATH.exists():
        print(f"Base de données introuvable : {DB_PATH}")
        sys.exit(1)

    with sqlite3.connect(DB_PATH) as conn:
        title, raw_chat, created_at = get_latest_chat(conn)

    messages = extract_clean_messages(raw_chat)
    if not messages:
        print(f"Aucun message publiable dans la session '{title}'.")
        return

    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    out = export_to_markdown(title, created_at, messages, dest)
    print(f"Session exportée avec succès : {out}")


if __name__ == "__main__":
    main()
