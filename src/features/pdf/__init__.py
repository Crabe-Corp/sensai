"""Module d'ingestion, d'audit et d'export de documents PDF pour SENSAI."""

from src.features.pdf.pdf_generator import (
    PDFExportResult,
    export_conversation_to_pdf,
    generate_pdf,
    resolve_pdf_export_path,
)
from src.features.pdf.pdf_reader import (
    PDFDocumentInfo,
    build_pdf_correction_prompt,
    build_pdf_historical_veracity_prompt,
    detect_and_prepare_pdf_audit,
    extract_text_from_pdf,
    find_pdf_path_in_text,
    read_pdf_file,
)

__all__ = [
    "PDFDocumentInfo",
    "PDFExportResult",
    "build_pdf_correction_prompt",
    "build_pdf_historical_veracity_prompt",
    "detect_and_prepare_pdf_audit",
    "export_conversation_to_pdf",
    "extract_text_from_pdf",
    "find_pdf_path_in_text",
    "generate_pdf",
    "read_pdf_file",
    "resolve_pdf_export_path",
]
