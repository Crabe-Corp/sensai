"""Tests for src/features/sec/security.py — mask_pii()

validate_input_with_llm() requires a live Ollama client and is not tested here.
"""
import sys
from pathlib import Path

import pytest

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from src.features.sec.security import mask_pii


# ---------------------------------------------------------------------------
# mask_pii — detection
# ---------------------------------------------------------------------------

class TestMaskPiiDetection:
    def test_clean_text_has_no_pii(self):
        _, has_pii = mask_pii("Quels étaient les 7 royaumes combattants ?")
        assert has_pii is False

    def test_detects_email(self):
        _, has_pii = mask_pii("Contactez admin@example.com pour plus d'infos.")
        assert has_pii is True

    def test_detects_french_mobile(self):
        _, has_pii = mask_pii("Mon numéro est le 06 12 34 56 78.")
        assert has_pii is True

    def test_detects_french_landline(self):
        _, has_pii = mask_pii("Appelez le 01.23.45.67.89 maintenant.")
        assert has_pii is True

    def test_detects_international_prefix(self):
        _, has_pii = mask_pii("Voici mon contact : +33 6 12 34 56 78.")
        assert has_pii is True

    def test_detects_multiple_pii(self):
        _, has_pii = mask_pii("Email: user@domain.fr, tél: 06 00 11 22 33.")
        assert has_pii is True


# ---------------------------------------------------------------------------
# mask_pii — masking
# ---------------------------------------------------------------------------

class TestMaskPiiMasking:
    def test_email_is_replaced(self):
        masked, _ = mask_pii("Contactez admin@example.com maintenant.")
        assert "admin@example.com" not in masked
        assert "[DONNÉE MASQUÉE]" in masked

    def test_phone_is_replaced(self):
        masked, _ = mask_pii("Numéro : 06 12 34 56 78")
        assert "06 12 34 56 78" not in masked
        assert "[DONNÉE MASQUÉE]" in masked

    def test_non_pii_content_is_preserved(self):
        text = "Li Si fut Premier ministre du Qin."
        masked, _ = mask_pii(text)
        assert masked == text

    def test_both_email_and_phone_replaced(self):
        text = "user@test.fr ou 06 11 22 33 44"
        masked, _ = mask_pii(text)
        assert "user@test.fr" not in masked
        assert "06 11 22 33 44" not in masked
        assert masked.count("[DONNÉE MASQUÉE]") == 2

    def test_empty_string_is_safe(self):
        masked, has_pii = mask_pii("")
        assert masked == ""
        assert has_pii is False

    def test_multiple_emails_all_replaced(self):
        text = "a@a.com et b@b.org sont concernés."
        masked, _ = mask_pii(text)
        assert "a@a.com" not in masked
        assert "b@b.org" not in masked
        assert masked.count("[DONNÉE MASQUÉE]") == 2
