"""Module d'ingestion et de traitement de documents PDF pour SENSAI."""

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
    "extract_text_from_pdf",
    "find_pdf_path_in_text",
    "build_pdf_correction_prompt",
    "build_pdf_historical_veracity_prompt",
    "detect_and_prepare_pdf_audit",
    "read_pdf_file",
]
