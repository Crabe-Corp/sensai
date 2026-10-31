"""Tests for src/features/sec/permissions.py

Covers:
- check(): deny-by-default, path confinement, extension filter, size limit
- safe_read(): denied / file missing / success
- safe_write(): denied / confirm rejected / confirm accepted / no confirm
- Audit log: every call produces a line in fs_audit.jsonl
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from src.features.sec.permissions import PROJECT_ROOT, RULES, check, safe_read, safe_write


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALLOWED_PATH = "battle_reports/test_changping.md"
FORBIDDEN_PATH_DIR = "secret/forbidden.md"
FORBIDDEN_EXT_PATH = "battle_reports/report.txt"


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Remove any file created during the test after it finishes."""
    yield
    for path in [ALLOWED_PATH]:
        target = PROJECT_ROOT / path
        if target.exists():
            target.unlink()


# ---------------------------------------------------------------------------
# check() — core permission logic
# ---------------------------------------------------------------------------

class TestCheck:
    def test_allowed_path_read(self):
        ok, reason = check(ALLOWED_PATH, "read")
        assert ok is True
        assert reason == "ok"

    def test_allowed_path_write(self):
        ok, reason = check(ALLOWED_PATH, "write")
        assert ok is True
        assert reason == "ok"

    def test_forbidden_directory_is_denied(self):
        ok, reason = check(FORBIDDEN_PATH_DIR, "read")
        assert ok is False
        assert "outside the allowed folders" in reason

    def test_path_traversal_is_denied(self):
        """../../etc/passwd style traversal must be blocked."""
        ok, reason = check("battle_reports/../../etc/passwd", "read")
        assert ok is False

    def test_forbidden_extension_is_denied(self):
        ok, reason = check(FORBIDDEN_EXT_PATH, "write")
        assert ok is False
        assert "Extension" in reason
        assert ".txt" in reason

    def test_file_too_large_is_denied(self):
        rule = RULES[0]
        ok, reason = check(ALLOWED_PATH, "write", size=rule.max_bytes + 1)
        assert ok is False
        assert "too large" in reason

    def test_file_exactly_at_limit_is_allowed(self):
        rule = RULES[0]
        ok, _ = check(ALLOWED_PATH, "write", size=rule.max_bytes)
        assert ok is True

    def test_targeting_directory_itself_is_denied(self):
        """Pointing directly at the allowed directory root (no file) must be denied (wrong extension)."""
        ok, reason = check("battle_reports", "read")
        assert ok is False

    def test_audit_log_is_written(self, tmp_path, monkeypatch):
        """Every call must append a JSON line to the audit log."""
        import src.features.sec.permissions as perm_mod

        audit = tmp_path / "audit.jsonl"
        monkeypatch.setattr(perm_mod, "AUDIT_LOG", audit)

        check(ALLOWED_PATH, "read")
        check(FORBIDDEN_PATH_DIR, "write")

        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert "op" in entry and "allowed" in entry and "path" in entry

    def test_audit_log_records_denied_attempt(self, tmp_path, monkeypatch):
        import src.features.sec.permissions as perm_mod

        audit = tmp_path / "audit.jsonl"
        monkeypatch.setattr(perm_mod, "AUDIT_LOG", audit)

        check(FORBIDDEN_PATH_DIR, "write")

        entry = json.loads(audit.read_text(encoding="utf-8").strip())
        assert entry["allowed"] is False


# ---------------------------------------------------------------------------
# safe_read()
# ---------------------------------------------------------------------------

class TestSafeRead:
    def test_denied_outside_allowed_dir(self):
        result = safe_read(FORBIDDEN_PATH_DIR)
        assert result["status"] == "denied"
        assert "reason" in result

    def test_missing_file_returns_error(self):
        result = safe_read(ALLOWED_PATH)  # file doesn't exist yet
        assert result["status"] == "error"
        assert "does not exist" in result["reason"]

    def test_reads_existing_file(self):
        target = PROJECT_ROOT / ALLOWED_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Bataille de Changping.", encoding="utf-8")

        result = safe_read(ALLOWED_PATH)
        assert result["status"] == "success"
        assert result["content"] == "Bataille de Changping."


# ---------------------------------------------------------------------------
# safe_write()
# ---------------------------------------------------------------------------

class TestSafeWrite:
    def test_denied_outside_allowed_dir(self):
        result = safe_write(FORBIDDEN_PATH_DIR, "content")
        assert result["status"] == "denied"

    def test_denied_wrong_extension(self):
        result = safe_write(FORBIDDEN_EXT_PATH, "content")
        assert result["status"] == "denied"

    def test_writes_without_confirm_callback(self):
        result = safe_write(ALLOWED_PATH, "Victoire de Qin.")
        assert result["status"] == "success"
        assert (PROJECT_ROOT / ALLOWED_PATH).read_text(encoding="utf-8") == "Victoire de Qin."

    def test_confirm_called_with_false_when_file_missing(self):
        received = []
        safe_write(ALLOWED_PATH, "content", confirm=lambda exists: received.append(exists) or True)
        assert received == [False]

    def test_confirm_called_with_true_when_file_exists(self):
        target = PROJECT_ROOT / ALLOWED_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old content", encoding="utf-8")

        received = []
        safe_write(ALLOWED_PATH, "new content", confirm=lambda exists: received.append(exists) or True)
        assert received == [True]

    def test_aborted_when_confirm_refuses(self):
        result = safe_write(ALLOWED_PATH, "Doit être rejeté.", confirm=lambda _: False)
        assert result["status"] == "aborted"
        assert not (PROJECT_ROOT / ALLOWED_PATH).exists()

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        """safe_write must create missing parent dirs inside the allowed zone."""
        import src.features.sec.permissions as perm_mod

        nested = "battle_reports/nested/deep/report.md"
        target = PROJECT_ROOT / nested
        try:
            result = safe_write(nested, "Contenu imbriqué.")
            assert result["status"] == "success"
            assert target.read_text(encoding="utf-8") == "Contenu imbriqué."
        finally:
            if target.exists():
                target.unlink()
            # Clean up created directories if empty
            for parent in target.parents:
                if parent == PROJECT_ROOT / "battle_reports":
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
