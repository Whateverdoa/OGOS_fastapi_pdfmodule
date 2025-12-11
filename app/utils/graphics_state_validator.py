"""
Graphics State Validator

Validates and optionally repairs q/Q (graphics state save/restore) balance
in PDF content streams. An imbalance causes downstream PDF processors like
iText7 to crash with "Stack empty" errors.

Usage:
    validator = GraphicsStateValidator()
    result = validator.validate_pdf(pdf_path)
    
    # Or validate and fix in one pass:
    validator.validate_and_fix_pdf(input_path, output_path)
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject


@dataclass
class ValidationResult:
    """Result of graphics state validation for a single stream."""

    xref: int
    q_count: int
    Q_count: int
    is_balanced: bool
    excess_Q: int  # Positive = more Q than q (causes stack underflow)


@dataclass
class PDFValidationResult:
    """Overall validation result for a PDF."""

    is_valid: bool
    total_streams: int
    imbalanced_streams: int
    stream_results: List[ValidationResult]
    error: Optional[str] = None


class GraphicsStateValidator:
    """Validates and repairs q/Q balance in PDF content streams."""

    def __init__(self, debug: bool = False):
        self.debug = debug

    def validate_pdf(self, pdf_path: str) -> PDFValidationResult:
        """
        Validate q/Q balance in all content streams of a PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            PDFValidationResult with details about any imbalances
        """
        try:
            doc = fitz.open(pdf_path)
            reader = PdfReader(pdf_path)

            stream_results: List[ValidationResult] = []
            imbalanced = 0

            # Collect all content stream xrefs
            xrefs = self._collect_content_xrefs(reader)

            for xref in xrefs:
                try:
                    content = doc.xref_stream(xref).decode("latin-1", errors="ignore")
                    q_count, Q_count = self._count_graphics_state_ops(content)
                    is_balanced = q_count == Q_count
                    excess_Q = Q_count - q_count

                    result = ValidationResult(
                        xref=xref,
                        q_count=q_count,
                        Q_count=Q_count,
                        is_balanced=is_balanced,
                        excess_Q=excess_Q,
                    )
                    stream_results.append(result)

                    if not is_balanced:
                        imbalanced += 1
                        if self.debug:
                            print(
                                f"Stream {xref}: q={q_count}, Q={Q_count}, "
                                f"excess_Q={excess_Q}"
                            )

                except Exception as e:
                    if self.debug:
                        print(f"Error reading stream {xref}: {e}")

            doc.close()

            return PDFValidationResult(
                is_valid=imbalanced == 0,
                total_streams=len(stream_results),
                imbalanced_streams=imbalanced,
                stream_results=stream_results,
            )

        except Exception as e:
            return PDFValidationResult(
                is_valid=False,
                total_streams=0,
                imbalanced_streams=0,
                stream_results=[],
                error=str(e),
            )

    def validate_and_fix_pdf(
        self, input_path: str, output_path: Optional[str] = None
    ) -> PDFValidationResult:
        """
        Validate and fix q/Q balance in a PDF.

        If there are more Q's than q's, prepends the necessary q's.
        If there are more q's than Q's, appends the necessary Q's.

        Args:
            input_path: Path to the input PDF
            output_path: Path for output PDF (defaults to overwriting input)

        Returns:
            PDFValidationResult after fixes applied
        """
        output_path = output_path or input_path

        # First validate
        initial_result = self.validate_pdf(input_path)

        if initial_result.is_valid:
            if self.debug:
                print("PDF already has balanced graphics state")
            return initial_result

        if initial_result.error:
            return initial_result

        # Fix imbalanced streams
        try:
            doc = fitz.open(input_path)

            for stream_result in initial_result.stream_results:
                if stream_result.is_balanced:
                    continue

                xref = stream_result.xref
                excess = stream_result.excess_Q

                try:
                    content = doc.xref_stream(xref).decode("latin-1", errors="ignore")

                    if excess > 0:
                        # More Q than q - prepend q's
                        prefix = "q\n" * excess
                        fixed_content = prefix + content
                        if self.debug:
                            print(f"Stream {xref}: prepending {excess} q's")
                    else:
                        # More q than Q - append Q's
                        suffix = "\nQ" * abs(excess)
                        fixed_content = content + suffix
                        if self.debug:
                            print(f"Stream {xref}: appending {abs(excess)} Q's")

                    doc.update_stream(xref, fixed_content.encode("latin-1"))

                except Exception as e:
                    if self.debug:
                        print(f"Error fixing stream {xref}: {e}")

            # Save the fixed PDF
            doc.save(output_path, deflate=True)
            doc.close()

            # Re-validate to confirm fix
            return self.validate_pdf(output_path)

        except Exception as e:
            return PDFValidationResult(
                is_valid=False,
                total_streams=initial_result.total_streams,
                imbalanced_streams=initial_result.imbalanced_streams,
                stream_results=initial_result.stream_results,
                error=f"Fix failed: {e}",
            )

    def _collect_content_xrefs(self, reader: PdfReader) -> List[int]:
        """Collect xrefs of all content streams (pages + Form XObjects)."""
        xrefs: Set[int] = set()

        for page in reader.pages:
            # Page contents
            contents = page.get("/Contents")
            if contents:
                xrefs.update(self._extract_xrefs(contents))

            # Form XObjects in resources
            resources = page.get("/Resources")
            xrefs.update(self._collect_form_xrefs(resources))

        return list(xrefs)

    def _collect_form_xrefs(self, resources) -> Set[int]:
        """Recursively collect xrefs from Form XObjects."""
        xrefs: Set[int] = set()

        if not resources:
            return xrefs

        try:
            res_obj = (
                resources.get_object()
                if hasattr(resources, "get_object")
                else resources
            )

            xobjects = res_obj.get("/XObject") if res_obj else None
            if not xobjects:
                return xrefs

            xobjects_obj = (
                xobjects.get_object()
                if hasattr(xobjects, "get_object")
                else xobjects
            )

            for name, value in xobjects_obj.items():
                form = (
                    value.get_object() if hasattr(value, "get_object") else value
                )

                if not isinstance(form, DictionaryObject):
                    continue

                if form.get("/Subtype") != "/Form":
                    continue

                # Get xref of this form
                if hasattr(value, "idnum"):
                    xrefs.add(value.idnum)

                # Recurse into form's resources
                form_resources = form.get("/Resources")
                xrefs.update(self._collect_form_xrefs(form_resources))

        except Exception:
            pass

        return xrefs

    def _extract_xrefs(self, obj) -> Set[int]:
        """Extract xref numbers from content object(s)."""
        xrefs: Set[int] = set()

        if obj is None:
            return xrefs

        if hasattr(obj, "idnum"):
            xrefs.add(obj.idnum)
            return xrefs

        if hasattr(obj, "get_object"):
            obj = obj.get_object()

        if isinstance(obj, list):
            for item in obj:
                xrefs.update(self._extract_xrefs(item))

        return xrefs

    def _count_graphics_state_ops(self, content: str) -> Tuple[int, int]:
        """
        Count q and Q operators in content stream.

        Returns:
            Tuple of (q_count, Q_count)
        """
        q_count = 0
        Q_count = 0

        for line in content.split("\n"):
            stripped = line.strip()

            # Match standalone q or Q operators
            if stripped == "q":
                q_count += 1
            elif stripped == "Q":
                Q_count += 1

            # Also check for q/Q in space-separated operator sequences
            # e.g., "q 1 0 0 1 0 0 cm" or "S Q"
            tokens = stripped.split()
            for token in tokens:
                if token == "q" and stripped != "q":
                    q_count += 1
                elif token == "Q" and stripped != "Q":
                    Q_count += 1

        return q_count, Q_count


