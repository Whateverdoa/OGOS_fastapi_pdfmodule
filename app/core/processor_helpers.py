"""
PDF Processor Helper Functions

Contains preprocessing, validation, and repair logic extracted from PDFProcessor.
"""

import os
import tempfile
from typing import Any, Dict, List, Tuple

from ..models.schemas import PDFJobConfig
from ..utils.pdf_repair import PDFRepair
from ..utils.pdf_utils import PDFUtils
from ..utils.winding_router import route_by_winding
from .pdf_analyzer import PDFAnalyzer


def validate_and_repair_pdf(pdf_repair: PDFRepair, pdf_path: str) -> Dict[str, Any]:
    """
    Validate PDF for content stream issues (q/Q imbalance) and repair if needed.

    This addresses the "Stack empty" exception in iText when PDFs have more
    Q (restore) operators than q (save) operators.

    Returns:
        Dictionary with repair info:
        - validated: True if validation was performed
        - issues_found: True if issues were detected
        - repaired: True if repair was attempted and successful
        - output_path: Path to repaired PDF (or original if no repair needed)
        - method: Repair method used
        - details: Validation details
    """
    result = {
        "validated": False,
        "issues_found": False,
        "repaired": False,
        "output_path": pdf_path,
        "method": None,
        "details": {},
    }

    try:
        validation = pdf_repair.validate_pdf(pdf_path)
        result["validated"] = True
        result["details"] = {
            "is_valid": validation.is_valid,
            "q_ops": validation.total_q_ops,
            "Q_ops": validation.total_Q_ops,
            "stack_underflows": validation.stack_underflows,
            "page_issues": validation.page_issues,
            "warnings": validation.warnings,
        }

        if not validation.is_valid or validation.has_stack_imbalance:
            result["issues_found"] = True

            temp_repaired = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            temp_repaired_path = temp_repaired.name
            temp_repaired.close()

            repair_result = pdf_repair.repair_pdf(pdf_path, temp_repaired_path)

            if repair_result.success and repair_result.output_path:
                result["repaired"] = True
                result["output_path"] = repair_result.output_path
                result["method"] = repair_result.method_used

                if repair_result.validation_after:
                    result["details"]["after_repair"] = {
                        "is_valid": repair_result.validation_after.is_valid,
                        "q_ops": repair_result.validation_after.total_q_ops,
                        "Q_ops": repair_result.validation_after.total_Q_ops,
                        "stack_underflows": repair_result.validation_after.stack_underflows,
                    }
            else:
                result["details"]["repair_error"] = repair_result.error
                try:
                    os.unlink(temp_repaired_path)
                except Exception:
                    pass

    except Exception as e:
        result["details"]["error"] = str(e)

    return result


def preprocess_dimensions_and_winding(
    pdf_utils: PDFUtils,
    analyzer: PDFAnalyzer,
    pdf_path: str,
    job_config: PDFJobConfig,
    analysis: Dict[str, Any],
) -> Tuple[str, PDFJobConfig, Dict[str, Any], List[str]]:
    """
    Pre-process PDF to handle dimension comparison and winding normalization.

    Returns:
        Tuple of (updated_pdf_path, updated_job_config, updated_analysis, warnings)
    """
    warnings: List[str] = []
    working_pdf_path = pdf_path

    box_coords_mm = analysis.get("trimbox") or analysis.get("mediabox")
    if not box_coords_mm:
        warnings.append("No trimbox or mediabox found in PDF")
        return working_pdf_path, job_config, analysis, warnings

    artwork_width = abs(box_coords_mm["x1"] - box_coords_mm["x0"])
    artwork_height = abs(box_coords_mm["y1"] - box_coords_mm["y0"])

    tolerance = 1.0
    order_width = float(job_config.width)
    order_height = float(job_config.height)

    width_matches = abs(artwork_width - order_width) <= tolerance
    height_matches = abs(artwork_height - order_height) <= tolerance
    width_matches_swapped = abs(artwork_width - order_height) <= tolerance
    height_matches_swapped = abs(artwork_height - order_width) <= tolerance

    dimensions_match = width_matches and height_matches
    dimensions_match_swapped = width_matches_swapped and height_matches_swapped

    current_winding = getattr(job_config, "winding", None)
    rotate_degrees = getattr(job_config, "rotate_degrees", None)

    rotation_angle = None
    if rotate_degrees is not None:
        rotation_angle = rotate_degrees
        warnings.append(f"Using rotation from ZIP pipeline: {rotation_angle}°")
    elif current_winding is not None and current_winding != 2:
        try:
            rotation_angle = route_by_winding(current_winding)
            warnings.append(
                f"Calculated rotation from winding {current_winding}: {rotation_angle}°"
            )
        except Exception as e:
            warnings.append(
                f"Error calculating rotation from winding {current_winding}: {str(e)}"
            )

    if rotation_angle and rotation_angle % 360 != 0:
        temp_rot = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_rot_path = temp_rot.name
        temp_rot.close()

        if pdf_utils.rotate_pdf(pdf_path, temp_rot_path, rotation_angle, flatten=True):
            working_pdf_path = temp_rot_path
            analysis = analyzer.analyze_pdf(working_pdf_path)

            box_coords_mm = analysis.get("trimbox") or analysis.get("mediabox")
            if box_coords_mm:
                actual_width = abs(box_coords_mm["x1"] - box_coords_mm["x0"])
                actual_height = abs(box_coords_mm["y1"] - box_coords_mm["y0"])
                job_config.width = actual_width
                job_config.height = actual_height
                warnings.append(
                    f"Rotated artwork {rotation_angle}° and updated dimensions "
                    f"to {actual_width:.1f}x{actual_height:.1f}mm"
                )
            else:
                warnings.append(f"Rotated artwork {rotation_angle}°")

            job_config.winding = 2
            warnings.append("Normalized winding to 2")
        else:
            warnings.append(f"Failed to rotate PDF by {rotation_angle}°")

    if not rotation_angle:
        if not dimensions_match:
            if dimensions_match_swapped:
                # Swap config dimensions to match PDF
                job_config.width = artwork_height
                job_config.height = artwork_width
                warnings.append(
                    f"Artwork dimensions ({artwork_width:.1f}x{artwork_height:.1f}mm) "
                    f"are swapped compared to order ({order_width:.1f}x{order_height:.1f}mm). "
                    f"Swapped config to {job_config.width:.1f}x{job_config.height:.1f}mm."
                )
            else:
                warnings.append(
                    f"Artwork dimensions ({artwork_width:.1f}x{artwork_height:.1f}mm) "
                    f"don't match order ({order_width:.1f}x{order_height:.1f}mm)"
                )

    return working_pdf_path, job_config, analysis, warnings


def validate_trimbox_dimensions(
    box_coords_mm: Dict[str, float], job_config: PDFJobConfig
) -> List[str]:
    """
    Validate that trimbox dimensions match job config dimensions.

    Returns:
        List of warning messages
    """
    warnings: List[str] = []

    if not box_coords_mm:
        warnings.append("No trimbox found for dimension validation")
        return warnings

    trimbox_width = abs(box_coords_mm["x1"] - box_coords_mm["x0"])
    trimbox_height = abs(box_coords_mm["y1"] - box_coords_mm["y0"])

    order_width = float(job_config.width)
    order_height = float(job_config.height)

    tolerance = 1.0

    width_matches = abs(trimbox_width - order_width) <= tolerance
    height_matches = abs(trimbox_height - order_height) <= tolerance

    if not (width_matches and height_matches):
        warnings.append(
            f"Trimbox dimensions ({trimbox_width:.1f}x{trimbox_height:.1f}mm) "
            f"don't match order dimensions ({order_width:.1f}x{order_height:.1f}mm) "
            f"after rotation/normalization. Stans placement may be incorrect."
        )

    return warnings

