from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.ollama_client import ChatMessage
from src.features.memory import ChatSession, SessionManager, SessionMetadata
from src.features.pdf import (
    PDFDocumentInfo,
    build_pdf_correction_prompt,
    extract_text_from_pdf,
    read_pdf_file,
)
from src.features.tools.executor import ToolExecutor
from src.features.tools.registry import default_registry
from src.interfaces.cli.commands.commands import Commands


def _create_sample_pdf(file_path: Path, text: str = "Bonjour monde de Qin.") -> Path:
    """Génère un fichier PDF 1.4 minimaliste et valide contenant du texte."""
    stream_content = f"BT\n/F1 12 Tf\n50 700 Td\n({text}) Tj\nET\n".encode("latin1", errors="replace")
    stream_len = len(stream_content)

    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        + f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("ascii")
        + stream_content
        + b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    xref_offset = len(body)
    xref_and_trailer = (
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000350 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    )

    file_path.write_bytes(body + xref_and_trailer)
    return file_path


def test_extract_text_from_pdf_valid(tmp_path: Path):
    pdf_path = _create_sample_pdf(tmp_path / "test_doc.pdf", "Les armees de Qin avancent vers Zhao.")
    info = extract_text_from_pdf(pdf_path)

    assert isinstance(info, PDFDocumentInfo)
    assert info.file_name == "test_doc.pdf"
    assert info.total_pages == 1
    assert info.extracted_pages == 1
    assert "Les armees de Qin avancent vers Zhao." in info.content
    assert not info.is_truncated


def test_extract_text_from_pdf_non_existent():
    with pytest.raises(FileNotFoundError, match="n'existe pas ou est inaccessible"):
        extract_text_from_pdf("dossier_inexistant/document_fantome.pdf")


def test_extract_text_from_pdf_invalid_extension(tmp_path: Path):
    txt_file = tmp_path / "document.txt"
    txt_file.write_text("Texte simple", encoding="utf-8")
    with pytest.raises(ValueError, match="n'est pas un document PDF"):
        extract_text_from_pdf(txt_file)


def test_extract_text_from_pdf_empty_file(tmp_path: Path):
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.touch()
    with pytest.raises(ValueError, match="est vide"):
        extract_text_from_pdf(empty_pdf)


def test_extract_text_from_pdf_truncation_limits(tmp_path: Path):
    long_text = "Histoire des sept royaumes. " * 30
    pdf_path = _create_sample_pdf(tmp_path / "long_doc.pdf", long_text)
    info = extract_text_from_pdf(pdf_path, max_chars=80)

    assert info.is_truncated
    assert len(info.content) <= 200


def test_build_pdf_correction_prompt_default_and_custom(tmp_path: Path):
    pdf_path = _create_sample_pdf(tmp_path / "conquete.pdf", "Le roi de Qin a unifie les royaumes.")
    info = extract_text_from_pdf(pdf_path)

    prompt_default = build_pdf_correction_prompt(info)
    assert "Tu es un relecteur et correcteur professionnel" in prompt_default
    assert "conquete.pdf" in prompt_default
    assert "Le roi de Qin a unifie les royaumes." in prompt_default
    assert "Corrections détaillées" in prompt_default

    prompt_custom = build_pdf_correction_prompt(info, custom_instruction="Corrige uniquement la ponctuation.")
    assert "Corrige uniquement la ponctuation." in prompt_custom


def test_read_pdf_file_helper(tmp_path: Path):
    pdf_path = _create_sample_pdf(tmp_path / "rapport.pdf", "Rapport trimestriel militaire.")
    res = read_pdf_file(str(pdf_path))

    assert res["status"] == "success"
    assert res["file_name"] == "rapport.pdf"
    assert "Rapport trimestriel militaire." in res["content"]

    err_res = read_pdf_file("fichier_introuvable.pdf")
    assert err_res["status"] == "error"
    assert "error" in err_res


def test_tool_read_pdf_document_in_registry(tmp_path: Path):
    pdf_path = _create_sample_pdf(tmp_path / "archive.pdf", "Extraits du Shiji de Sima Qian.")
    executor = ToolExecutor(default_registry)

    result = executor.execute("read_pdf_document", {"file_path": str(pdf_path)})
    assert result.success
    assert isinstance(result.result, dict)
    assert result.result.get("status") == "success"
    assert "Shiji" in result.result.get("content", "")


def test_find_pdf_path_in_text(tmp_path: Path):
    from src.features.pdf import find_pdf_path_in_text

    pdf_file = _create_sample_pdf(tmp_path / "chronique.pdf", "Texte historique")

    # Détection avec guillemets
    found1 = find_pdf_path_in_text(f'Regarde ce document : "{pdf_file}" et dis-moi ce que tu en penses.')
    assert found1 is not None
    assert found1.resolve() == pdf_file.resolve()

    # Détection sans guillemets
    found2 = find_pdf_path_in_text(f"Analyse {pdf_file} s'il te plait.")
    assert found2 is not None
    assert found2.resolve() == pdf_file.resolve()

    # Fichier inexistant
    assert find_pdf_path_in_text("Ceci parle de document_inexistant.pdf sans fichier réel.") is None


def test_detect_and_prepare_pdf_audit(tmp_path: Path):
    from src.features.pdf import detect_and_prepare_pdf_audit

    pdf_file = _create_sample_pdf(tmp_path / "bataille.pdf", "La bataille de Changping a eu lieu en -260.")
    prompt = f'Peux-tu vérifier la véracité historique de "{pdf_file}" concernant Bai Qi ?'

    result = detect_and_prepare_pdf_audit(prompt)
    assert result is not None
    path, instruction, pdf_info = result
    assert path.resolve() == pdf_file.resolve()
    assert "véracité historique" in instruction
    assert "Bai Qi" in instruction
    assert "Changping" in pdf_info.content


def test_build_pdf_historical_veracity_prompt(tmp_path: Path):
    from src.features.pdf import build_pdf_historical_veracity_prompt, extract_text_from_pdf

    pdf_file = _create_sample_pdf(tmp_path / "doc_test.pdf", "L'armee de Qin comptait 20000 hommes.")
    info = extract_text_from_pdf(pdf_file)

    prompt = build_pdf_historical_veracity_prompt(info, "Vérifie les effectifs.")
    assert "7 Grands Royaumes Combattants" in prompt
    assert "Wan" in prompt
    assert "facteur 10" in prompt
    assert "doc_test.pdf" in prompt
    assert "armee de Qin comptait 20000 hommes." in prompt


def test_tool_verify_pdf_historical_veracity(tmp_path: Path):
    pdf_file = _create_sample_pdf(tmp_path / "sources.pdf", "Chroniques des Royaumes.")
    executor = ToolExecutor(default_registry)

    res = executor.execute("verify_pdf_historical_veracity", {"file_path": str(pdf_file), "focus_topic": "Changping"})
    assert res.success
    assert isinstance(res.result, dict)
    assert res.result.get("status") == "success"
    assert "Wan" in res.result.get("instructions", "")
    assert res.result.get("focus_topic") == "Changping"


def test_cli_natural_sentence_detects_pdf_and_launches_veracity_audit(tmp_path: Path, capsys):
    from unittest.mock import patch
    from src.core.engine import TokenChunkEvent
    from src.interfaces.cli.main import run_session

    pdf_file = _create_sample_pdf(tmp_path / "chronique_inconnue.pdf", "Bai Qi commandait les armees.")

    mock_client = MagicMock()
    # Mock du classificateur de sécurité pour autoriser le message
    mock_client.chat_structured.return_value = MagicMock(is_valid=True)

    def fake_stream(messages, model, tools=None):
        sent_content = messages[-1].content
        assert "7 Grands Royaumes Combattants" in sent_content
        assert "chronique_inconnue.pdf" in sent_content
        yield TokenChunkEvent(token="Audit historique : Bai Qi était un général de Qin.")

    user_inputs = [f'Voici mon manuscrit : "{pdf_file}", vérifie si les faits sont exacts.', "/exit"]

    with patch("builtins.input", side_effect=user_inputs), \
         patch("src.core.engine.ConversationEngine.run_stream", side_effect=fake_stream):
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434", rag_enabled=False)

    out = capsys.readouterr().out
    assert ("[PDF Détecté]" in out or "[PDF Detected]" in out)
    assert "chronique_inconnue.pdf" in out
    assert ("Audit de la véracité historique..." in out or "Historical veracity audit..." in out)
    assert "Audit historique : Bai Qi était un général de Qin." in out

