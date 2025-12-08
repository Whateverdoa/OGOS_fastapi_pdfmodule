# PDF Utilities
from .pdf_repair import PDFRepair, validate_pdf, repair_pdf, ValidationResult, RepairResult
from .pdf_utils import (
    PDFUtils,
    merge_pdfs,
    ensure_overprint_for_spot,
    embed_all_fonts,
    outline_all_fonts,
    has_unembedded_fonts,
    rotate_pdf,
    extract_page,
    remove_spot_color_objects,
    get_pdf_info,
)

__all__ = [
    # Repair utilities
    "PDFRepair",
    "validate_pdf",
    "repair_pdf",
    "ValidationResult",
    "RepairResult",
    # PDF utilities (facade class)
    "PDFUtils",
    # PDF utilities (direct functions)
    "merge_pdfs",
    "ensure_overprint_for_spot",
    "embed_all_fonts",
    "outline_all_fonts",
    "has_unembedded_fonts",
    "rotate_pdf",
    "extract_page",
    "remove_spot_color_objects",
    "get_pdf_info",
]

