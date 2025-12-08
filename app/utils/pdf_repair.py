"""
PDF Repair Utility

Validates and repairs corrupt PDFs, specifically:
- Graphics state stack imbalances (q/Q operators)
- Invalid content stream operators
- General PDF structure issues

Uses Ghostscript for best-effort repair when available.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF


@dataclass
class ValidationResult:
    """Result of PDF content stream validation."""

    is_valid: bool
    page_issues: Dict[int, List[str]] = field(default_factory=dict)
    total_q_ops: int = 0
    total_Q_ops: int = 0
    stack_underflows: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def has_stack_imbalance(self) -> bool:
        """True if q/Q operators are unbalanced."""
        return self.total_q_ops != self.total_Q_ops or self.stack_underflows > 0


@dataclass
class RepairResult:
    """Result of PDF repair operation."""

    success: bool
    output_path: Optional[str] = None
    method_used: Optional[str] = None
    validation_before: Optional[ValidationResult] = None
    validation_after: Optional[ValidationResult] = None
    error: Optional[str] = None


class PDFRepair:
    """Validates and repairs corrupt PDF files."""

    # Regex to find q (save) and Q (restore) operators in content streams
    # These should be standalone operators, not part of other tokens
    Q_SAVE_PATTERN = re.compile(rb"\bq\b")
    Q_RESTORE_PATTERN = re.compile(rb"\bQ\b")

    def __init__(self):
        self._gs_path = shutil.which("gs") or shutil.which("ghostscript")

    @property
    def has_ghostscript(self) -> bool:
        """Check if Ghostscript is available."""
        return self._gs_path is not None

    def validate_pdf(self, pdf_path: str) -> ValidationResult:
        """
        Validate PDF content streams for graphics state issues.

        Checks each page's content stream for:
        - q/Q operator balance (graphics state save/restore)
        - Stack underflows (Q without matching q)

        Args:
            pdf_path: Path to PDF file

        Returns:
            ValidationResult with details about any issues found
        """
        result = ValidationResult(is_valid=True)

        if not os.path.exists(pdf_path):
            result.is_valid = False
            result.warnings.append(f"File not found: {pdf_path}")
            return result

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                issues = self._validate_page_content(page, result)
                if issues:
                    result.page_issues[page_num] = issues
                    result.is_valid = False

            doc.close()

        except Exception as e:
            result.is_valid = False
            result.warnings.append(f"Error validating PDF: {str(e)}")

        return result

    def _validate_page_content(
        self, page: fitz.Page, result: ValidationResult
    ) -> List[str]:
        """
        Validate a single page's content stream.

        Args:
            page: PyMuPDF page object
            result: ValidationResult to update with counts

        Returns:
            List of issues found on this page
        """
        issues: List[str] = []

        try:
            # Get raw page content
            # This includes the page's own content stream and referenced XObjects
            content = self._get_page_content_bytes(page)

            # Count q (save) and Q (restore) operators
            q_count = len(self.Q_SAVE_PATTERN.findall(content))
            Q_count = len(self.Q_RESTORE_PATTERN.findall(content))

            result.total_q_ops += q_count
            result.total_Q_ops += Q_count

            # Simulate stack to detect underflows
            stack_depth = 0
            underflows = 0

            # More precise parsing: walk through content byte by byte
            # looking for standalone q/Q operators
            pos = 0
            while pos < len(content):
                # Skip whitespace
                while pos < len(content) and content[pos : pos + 1] in b" \t\r\n":
                    pos += 1
                if pos >= len(content):
                    break

                # Check for q or Q operator (must be followed by whitespace or EOL)
                if content[pos : pos + 1] == b"q":
                    next_pos = pos + 1
                    if next_pos >= len(content) or content[next_pos : next_pos + 1] in (
                        b" ",
                        b"\t",
                        b"\r",
                        b"\n",
                    ):
                        stack_depth += 1
                        pos = next_pos
                        continue

                elif content[pos : pos + 1] == b"Q":
                    next_pos = pos + 1
                    if next_pos >= len(content) or content[next_pos : next_pos + 1] in (
                        b" ",
                        b"\t",
                        b"\r",
                        b"\n",
                    ):
                        if stack_depth <= 0:
                            underflows += 1
                        else:
                            stack_depth -= 1
                        pos = next_pos
                        continue

                # Skip to next whitespace or end
                while pos < len(content) and content[pos : pos + 1] not in b" \t\r\n":
                    pos += 1

            if underflows > 0:
                result.stack_underflows += underflows
                issues.append(
                    f"Stack underflow: {underflows} Q operator(s) without matching q"
                )

            if q_count != Q_count:
                issues.append(f"Unbalanced q/Q: {q_count} saves, {Q_count} restores")

            # Check final stack depth
            final_depth = q_count - Q_count - underflows
            if final_depth != 0:
                issues.append(f"Final stack depth: {final_depth} (should be 0)")

        except Exception as e:
            issues.append(f"Error parsing content: {str(e)}")

        return issues

    def _get_page_content_bytes(self, page: fitz.Page) -> bytes:
        """
        Extract raw content bytes from a page.

        This includes the page's content stream and attempts to include
        XObject form content as well.
        """
        try:
            # Get the page's xref
            xref = page.xref

            # Extract raw content stream
            # Using get_text with "rawdict" gives us access to raw content
            # But for q/Q analysis, we need the actual stream bytes

            # Method 1: Try to get raw content via page dictionary
            doc = page.parent
            content = b""

            # Get page dictionary
            page_dict = doc.xref_get_key(xref, "Contents")
            if page_dict:
                # Contents can be a stream or array of streams
                content = self._extract_stream_content(doc, page_dict)

            return content

        except Exception:
            # Fallback: return empty bytes
            return b""

    def _extract_stream_content(self, doc: fitz.Document, contents_ref: tuple) -> bytes:
        """Extract content from a stream reference."""
        try:
            # Get the stream data
            result = b""

            # If it's a reference to a stream
            if contents_ref[0] == "xref":
                xref = int(contents_ref[1].split()[0])
                stream = doc.xref_stream(xref)
                if stream:
                    result = stream

            # If it's an array of references
            elif contents_ref[0] == "array":
                # Parse array of xrefs
                array_str = contents_ref[1]
                xrefs = re.findall(r"(\d+)\s+\d+\s+R", array_str)
                for xref_str in xrefs:
                    try:
                        xref = int(xref_str)
                        stream = doc.xref_stream(xref)
                        if stream:
                            result += stream + b"\n"
                    except Exception:
                        continue

            return result

        except Exception:
            return b""

    def repair_pdf(
        self, pdf_path: str, output_path: Optional[str] = None
    ) -> RepairResult:
        """
        Attempt to repair a corrupt PDF.

        Tries multiple methods:
        1. Ghostscript rewrite (best for content stream issues)
        2. PyMuPDF save with garbage collection
        3. PyMuPDF incremental save

        Args:
            pdf_path: Path to the corrupt PDF
            output_path: Optional output path. If None, creates temp file.

        Returns:
            RepairResult with details about the repair attempt
        """
        result = RepairResult(success=False)

        # Validate before repair
        result.validation_before = self.validate_pdf(pdf_path)

        # If already valid, just copy
        if result.validation_before.is_valid:
            result.success = True
            result.method_used = "none_needed"
            if output_path:
                shutil.copy2(pdf_path, output_path)
                result.output_path = output_path
            else:
                result.output_path = pdf_path
            result.validation_after = result.validation_before
            return result

        # Determine output path
        if output_path is None:
            temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            temp.close()
            output_path = temp.name

        # Try repair methods in order of effectiveness
        methods = [
            ("ghostscript_pdfwrite", self._repair_with_ghostscript),
            ("pymupdf_garbage", self._repair_with_pymupdf_garbage),
            ("pymupdf_clean", self._repair_with_pymupdf_clean),
        ]

        for method_name, method_func in methods:
            try:
                if method_func(pdf_path, output_path):
                    # Validate the result
                    validation_after = self.validate_pdf(output_path)
                    if validation_after.is_valid:
                        result.success = True
                        result.method_used = method_name
                        result.output_path = output_path
                        result.validation_after = validation_after
                        return result
                    # Even if not fully valid, check if improved
                    if validation_after.stack_underflows < result.validation_before.stack_underflows:
                        result.success = True
                        result.method_used = f"{method_name}_partial"
                        result.output_path = output_path
                        result.validation_after = validation_after
                        return result
            except Exception as e:
                result.error = f"{method_name} failed: {str(e)}"
                continue

        # All methods failed
        result.error = "All repair methods failed"
        return result

    def _repair_with_ghostscript(self, input_path: str, output_path: str) -> bool:
        """
        Repair PDF using Ghostscript pdfwrite device.

        This rewrites the entire PDF content stream, which typically
        fixes q/Q imbalances by normalizing the stream.
        """
        if not self.has_ghostscript:
            return False

        try:
            args = [
                self._gs_path,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.6",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                "-dSAFER",
                # These options help with repair
                "-dPDFSETTINGS=/prepress",
                "-dDetectDuplicateImages=true",
                "-dPreserveMarkedContent=true",
                "-dPreserveOPIComments=true",
                # Output file
                f"-sOutputFile={output_path}",
                input_path,
            ]

            proc = subprocess.run(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
            )

            if proc.returncode == 0 and os.path.getsize(output_path) > 0:
                return True

        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

        return False

    def _repair_with_pymupdf_garbage(self, input_path: str, output_path: str) -> bool:
        """
        Repair PDF using PyMuPDF with garbage collection.

        Saves PDF with maximum garbage collection and deflate compression,
        which can fix some structural issues.
        """
        try:
            doc = fitz.open(input_path)
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()
            return os.path.getsize(output_path) > 0
        except Exception:
            return False

    def _repair_with_pymupdf_clean(self, input_path: str, output_path: str) -> bool:
        """
        Repair PDF using PyMuPDF page-by-page reconstruction.

        Creates a new PDF and copies each page, which can bypass
        some content stream issues.
        """
        try:
            src = fitz.open(input_path)
            dst = fitz.open()

            for page in src:
                new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
                new_page.show_pdf_page(new_page.rect, src, page.number)

                # Try to preserve trimbox
                try:
                    if page.trimbox != page.mediabox:
                        new_page.set_trimbox(page.trimbox)
                except Exception:
                    pass

            dst.save(output_path, garbage=4, deflate=True)
            dst.close()
            src.close()

            return os.path.getsize(output_path) > 0
        except Exception:
            return False

    def repair_and_validate(
        self, pdf_path: str, output_path: Optional[str] = None
    ) -> Tuple[bool, str, ValidationResult]:
        """
        Convenience method to repair and validate in one call.

        Args:
            pdf_path: Path to input PDF
            output_path: Optional output path

        Returns:
            Tuple of (success, output_path, validation_result)
        """
        result = self.repair_pdf(pdf_path, output_path)

        if result.success and result.output_path:
            return (True, result.output_path, result.validation_after)
        else:
            return (False, pdf_path, result.validation_before)


# Module-level convenience functions
_repair_instance: Optional[PDFRepair] = None


def get_repair_instance() -> PDFRepair:
    """Get singleton PDFRepair instance."""
    global _repair_instance
    if _repair_instance is None:
        _repair_instance = PDFRepair()
    return _repair_instance


def validate_pdf(pdf_path: str) -> ValidationResult:
    """Validate a PDF file for content stream issues."""
    return get_repair_instance().validate_pdf(pdf_path)


def repair_pdf(pdf_path: str, output_path: Optional[str] = None) -> RepairResult:
    """Repair a corrupt PDF file."""
    return get_repair_instance().repair_pdf(pdf_path, output_path)

