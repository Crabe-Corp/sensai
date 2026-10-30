import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# src/features/sec/permissions.py: parents[0]=sec, [1]=features, [2]=src, [3]=repository root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
AUDIT_LOG = PROJECT_ROOT / "logs" / "fs_audit.jsonl"

@dataclass(frozen=True)
class Rule:
    directory: str
    can_read: bool
    can_write: bool
    extensions: tuple[str, ...]
    max_bytes: int = 200_000

RULES = (
    Rule("battle_reports", can_read=True, can_write=True, extensions=(".md",)),
)

def check(path: str, op: str, size: int = 0) -> tuple[bool, str]:
    """Deny-by-default. Returns (allowed, reason); the reason is sent back to the LLM."""
    target = (PROJECT_ROOT / path).resolve()  # resolves .., symlinks, and neutralises absolute paths
    allowed_dirs = ", ".join(f"{r.directory}/" for r in RULES)
    ok, reason = False, f"'{path}' is outside the allowed folders ({allowed_dirs})."
    for r in RULES:
        base = (PROJECT_ROOT / r.directory).resolve()
        if base != target and base not in target.parents:
            continue
        if op == "write" and not r.can_write:
            reason = f"Writing is forbidden in '{r.directory}/' (read-only)."
        elif op == "read" and not r.can_read:
            reason = f"Reading is forbidden in '{r.directory}/'."
        elif target.suffix not in r.extensions:
            reason = f"Extension '{target.suffix}' is not allowed, allowed: {r.extensions}."
        elif size > r.max_bytes:
            reason = f"File too large ({size} > {r.max_bytes} bytes)."
        else:
            ok, reason = True, "ok"
        break
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "op": op, "path": str(target),
                            "allowed": ok, "reason": reason}, ensure_ascii=False) + "\n")
    return ok, reason

def safe_read(path: str) -> dict:
    """Read a file after checking the permissions."""
    ok, reason = check(path, "read")
    if not ok:
        return {"status": "denied", "reason": reason}
    target = (PROJECT_ROOT / path).resolve()
    if not target.is_file():
        return {"status": "error", "reason": f"{path} does not exist."}
    return {"status": "success", "content": target.read_text(encoding="utf-8")}

def safe_write(path: str, content: str, confirm: Callable[[bool], bool] | None = None) -> dict:
    """Write a file after checking the permissions.
    confirm(exists) is called once the permissions are validated, right before writing."""
    ok, reason = check(path, "write", size=len(content.encode()))
    if not ok:
        return {"status": "denied", "reason": reason}
    target = (PROJECT_ROOT / path).resolve()
    if confirm and not confirm(target.exists()):
        return {"status": "aborted", "message": "The user refused to save the file."}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"status": "success", "path": path}
