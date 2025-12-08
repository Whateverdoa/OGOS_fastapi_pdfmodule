"""
PDF Utilities - Facade Module

This module provides backwards-compatible access to PDF utility functions.
The actual implementations have been split into focused modules:

- pdf_merge.py: PDF merging/overlay operations
- pdf_overprint.py: Spot color overprint handling
- pdf_fonts.py: Font embedding, outlining, and detection
- pdf_rotation.py: Page rotation with box preservation
- pdf_info.py: PDF information extraction and page operations
"""

from typing import Dict, Optional

from .pdf_fonts import embed_all_fonts, has_unembedded_fonts, outline_all_fonts
from .pdf_info import extract_page, get_pdf_info, remove_spot_color_objects
from .pdf_merge import merge_pdfs
from .pdf_overprint import ensure_overprint_for_spot
from .pdf_rotation import rotate_pdf


class PDFUtils:
    """
    Utility class for PDF manipulation.

    This class provides static method wrappers around the modular PDF utilities
    for backwards compatibility. New code should import functions directly from
    the specific modules (pdf_merge, pdf_fonts, etc.).
    """

    @staticmethod
    def merge_pdfs(base_pdf_path: str, overlay_pdf_path: str, output_path: str) -> bool:
        """Merge two PDFs, overlaying the second on the first."""
        return merge_pdfs(base_pdf_path, overlay_pdf_path, output_path)

    @staticmethod
    def ensure_overprint_for_spot(pdf_path: str, spot_name: str = "stans") -> bool:
        """Ensure overprint is enabled for spot color operations."""
        return ensure_overprint_for_spot(pdf_path, spot_name)

    @staticmethod
    def embed_all_fonts(pdf_path: str) -> bool:
        """Embed all fonts using Ghostscript."""
        return embed_all_fonts(pdf_path)

    @staticmethod
    def outline_all_fonts(pdf_path: str) -> bool:
        """Convert all text to vector outlines using Ghostscript."""
        return outline_all_fonts(pdf_path)

    @staticmethod
    def has_unembedded_fonts(pdf_path: str) -> bool:
        """Check if PDF has unembedded fonts."""
        return has_unembedded_fonts(pdf_path)

    @staticmethod
    def rotate_pdf(
        input_path: str,
        output_path: str,
        angle: int,
        flatten: bool = False,
    ) -> bool:
        """Rotate all pages by the given angle."""
        return rotate_pdf(input_path, output_path, angle, flatten)

    @staticmethod
    def extract_page(pdf_path: str, page_num: int = 0) -> Optional[str]:
        """Extract a single page from a PDF."""
        return extract_page(pdf_path, page_num)

    @staticmethod
    def remove_spot_color_objects(pdf_path: str, output_path: str) -> bool:
        """Remove spot color objects from a PDF."""
        return remove_spot_color_objects(pdf_path, output_path)

    @staticmethod
    def get_pdf_info(pdf_path: str) -> Dict:
        """Get basic information about a PDF."""
        return get_pdf_info(pdf_path)


# Re-export all functions for direct import
__all__ = [
    "PDFUtils",
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
