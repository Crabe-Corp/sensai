from __future__ import annotations
import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from src.core.ollama_client import ChatMessage


class PDFExportResult(BaseModel):
    status: str
    file_name: str
    file_path: str
    file_size_bytes: int = 0
    pages_count: int = 1
    message: str = ""


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 40, 541, 40)
        self.drawString(54, 28, "SENSAI — Chroniques et Archives Historiques")
        self.drawRightString(541, 28, f"Page {self._pageNumber} / {total_pages}")
        self.restoreState()


def _format_markdown_inline(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`(.+?)`", r'<font name="Courier">\1</font>', escaped)
    return escaped


def _build_pdf_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=sample["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#8B1E0F"),
        alignment=0,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=sample["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#718096"),
        spaceAfter=12,
    )
    h1_style = ParagraphStyle(
        "SectionH1",
        parent=sample["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1A365D"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )
    h2_style = ParagraphStyle(
        "SectionH2",
        parent=sample["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#2C5282"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    h3_style = ParagraphStyle(
        "SectionH3",
        parent=sample["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#2D3748"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        "BulletDark",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        leftIndent=14,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=3,
    )
    quote_style = ParagraphStyle(
        "QuoteBlock",
        parent=sample["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        leftIndent=15,
        textColor=colors.HexColor("#4A5568"),
        spaceBefore=4,
        spaceAfter=6,
    )

    return {
        "title": title_style,
        "meta": meta_style,
        "h1": h1_style,
        "h2": h2_style,
        "h3": h3_style,
        "body": body_style,
        "bullet": bullet_style,
        "quote": quote_style,
    }


def _parse_content_to_story(content: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = []
    lines = content.strip().splitlines()

    i = 0
    while i < len(lines):
        raw_line = lines[i].rstrip()
        stripped = raw_line.strip()

        if not stripped:
            story.append(Spacer(1, 6))
            i += 1
            continue

        if stripped.startswith("---") or stripped.startswith("==="):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E0"), spaceAfter=8))
            i += 1
            continue

        if stripped.startswith("#### "):
            story.append(Paragraph(_format_markdown_inline(stripped[5:]), styles["h3"]))
            i += 1
            continue

        if stripped.startswith("### "):
            story.append(Paragraph(_format_markdown_inline(stripped[4:]), styles["h2"]))
            i += 1
            continue

        if stripped.startswith("## "):
            story.append(Paragraph(_format_markdown_inline(stripped[3:]), styles["h1"]))
            i += 1
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(_format_markdown_inline(stripped[2:]), styles["h1"]))
            i += 1
            continue

        if stripped.startswith(("- ", "* ", "• ")):
            item_text = _format_markdown_inline(stripped[2:].strip())
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{item_text}", styles["bullet"]))
            i += 1
            continue

        if re.match(r"^\d+\.\s+", stripped):
            num_match = re.match(r"^(\d+\.)\s+(.+)$", stripped)
            if num_match:
                prefix, item_text = num_match.groups()
                story.append(Paragraph(f"<b>{prefix}</b>&nbsp;&nbsp;{_format_markdown_inline(item_text)}", styles["bullet"]))
            i += 1
            continue

        if stripped.startswith("> "):
            quote_text = _format_markdown_inline(stripped[2:].strip())
            story.append(Paragraph(quote_text, styles["quote"]))
            i += 1
            continue
        para_lines = [stripped]
        while (
            i + 1 < len(lines)
            and lines[i + 1].strip()
            and not lines[i + 1].strip().startswith(("#", "-", "*", "•", ">", "---", "==="))
            and not re.match(r"^\d+\.\s+", lines[i + 1].strip())
        ):
            i += 1
            para_lines.append(lines[i].strip())

        full_para = " ".join(para_lines)
        story.append(Paragraph(_format_markdown_inline(full_para), styles["body"]))
        i += 1

    return story


def resolve_pdf_export_path(file_path: str | Path) -> Path:
    target = Path(file_path)
    if not target.parent.name and not target.is_absolute():
        target = Path("exports") / target

    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")

    target.parent.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def generate_pdf(file_path: str | Path, title: str, content: str, author: str = "SENSAI Historical Advisor") -> PDFExportResult:
    """Génère et exporte un document PDF mis en page avec en-têtes, pagination et typographie adaptée.
    PARAMS: - file_path - STR | PATH: chemin ou nom de fichier cible
            - title - STR: titre principal du document
            - content - STR: corps du document au format texte ou markdown
            - author - STR: nom de l'auteur ou conseiller
    RETURN: objet PDFExportResult avec le chemin résolu, la taille et le nombre de pages"""
    if not title or not title.strip():
        raise ValueError("Le titre du document PDF ne peut pas être vide.")

    if not content or not content.strip():
        raise ValueError("Le contenu du document PDF ne peut pas être vide.")

    target_path = resolve_pdf_export_path(file_path)
    styles = _build_pdf_styles()

    story: list[Any] = []
    story.append(Paragraph(_format_markdown_inline(title), styles["title"]))

    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
    meta_info = f"Émis par <b>{html.escape(author)}</b> &bull; Date : {now_str}"
    story.append(Paragraph(meta_info, styles["meta"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#8B1E0F"), spaceAfter=14))

    body_story = _parse_content_to_story(content, styles)
    story.extend(body_story)

    doc = SimpleDocTemplate(
        str(target_path),
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    doc.build(story, canvasmaker=NumberedCanvas)

    pages_count = 1
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(target_path))
        pages_count = len(reader.pages)
    except Exception:
        pass

    file_size = target_path.stat().st_size if target_path.is_file() else 0
    return PDFExportResult(status="success", file_name=target_path.name, file_path=str(target_path), file_size_bytes=file_size, pages_count=pages_count, message=f"Document PDF généré avec succès dans '{target_path.name}' ({pages_count} page(s), {file_size} octets).")


def export_conversation_to_pdf(messages: list[ChatMessage], file_path: str | Path, title: str = "Compte-rendu de Session — SENSAI", author: str = "SENSAI Historical Advisor") -> PDFExportResult:
    """Exporte une conversation épurée de ses commandes techniques au format PDF."""
    lines: list[str] = []
    for msg in messages:
        if msg.role == "system":
            continue
        stripped = msg.content.strip()
        if stripped.startswith(("/", "You > /")):
            continue

        speaker = "Utilisateur" if msg.role == "user" else "Conseiller Historique SENSAI"
        lines.append(f"### {speaker}")
        lines.append(stripped)
        lines.append("")
    if not lines:
        lines = ["Aucun échange conversationnel à exporter."]
    return generate_pdf(file_path=file_path, title=title, content="\n".join(lines), author=author)
