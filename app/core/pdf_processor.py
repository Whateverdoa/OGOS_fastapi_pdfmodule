"""
PDF Processor - Main Orchestrator

Processes PDFs according to job configuration: validates, repairs,
applies dielines (custom/circle/rectangle), and handles spot colors.
"""

import logging
import traceback
from typing import Any, Dict, List

from ..models.schemas import PDFJobConfig, ShapeType
from ..utils.pdf_repair import PDFRepair
from ..utils.pdf_utils import PDFUtils
from ..utils.winding_router import route_by_winding, route_by_winding_str
from .pdf_analyzer import PDFAnalyzer
from .processor_helpers import (
    preprocess_dimensions_and_winding,
    validate_and_repair_pdf,
    validate_trimbox_dimensions,
)
from .shape_processing import ShapeProcessor

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Main PDF processing orchestrator."""

    MM_TO_POINTS = 2.83465

    def __init__(self):
        self.analyzer = PDFAnalyzer()
        self.pdf_utils = PDFUtils()
        self.pdf_repair = PDFRepair()
        self.shape_processor = ShapeProcessor()

    def process_pdf(self, pdf_path: str, job_config: PDFJobConfig) -> Dict[str, Any]:
        """Process a PDF according to the job configuration."""
        try:
            # Step 0: Validate and repair PDF if needed (q/Q stack issues)
            working_pdf_path = pdf_path
            repair_info = validate_and_repair_pdf(self.pdf_repair, pdf_path)
            if repair_info.get("repaired"):
                working_pdf_path = repair_info["output_path"]

            # Step 1: Analyze the PDF
            analysis = self.analyzer.analyze_pdf(working_pdf_path)
            original_trimbox_mm = analysis.get("trimbox")

            # Step 1.5: Pre-processing - dimension comparison and winding normalization
            working_pdf_path, job_config, analysis, dimension_warnings = (
                preprocess_dimensions_and_winding(
                    self.pdf_utils,
                    self.analyzer,
                    working_pdf_path,
                    job_config,
                    analysis,
                )
            )

            # Get box coordinates for shape generation
            box_coords_mm, box_coords = self._get_box_coordinates(
                analysis, original_trimbox_mm
            )

            # Compute winding route
            winding_route = self._get_winding_route(job_config)

            # Step 2: Validate trimbox dimensions
            trimbox_warnings = validate_trimbox_dimensions(box_coords_mm, job_config)
            dimension_warnings.extend(trimbox_warnings)

            # Step 3: Process based on shape type
            if job_config.shape == ShapeType.custom:
                output_path = self.shape_processor.process_custom_shape(
                    working_pdf_path, job_config, analysis
                )
            else:
                output_path = self.shape_processor.process_standard_shape(
                    working_pdf_path, job_config, analysis, box_coords
                )

            return self._build_success_response(
                job_config,
                output_path,
                analysis,
                winding_route,
                dimension_warnings,
                repair_info,
            )

        except Exception as e:
            # Log full traceback for debugging while returning clean error to caller
            logger.error(
                "PDF processing failed for reference=%s path=%s: %s",
                job_config.reference,
                pdf_path,
                str(e),
                exc_info=True,
            )
            return {
                "success": False,
                "message": f"Error processing PDF: {str(e)}",
                "reference": job_config.reference,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

    def _get_box_coordinates(
        self, analysis: Dict[str, Any], original_trimbox_mm: Dict[str, float] | None
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        """Get box coordinates in mm and points."""
        box_coords_mm = analysis.get("trimbox")
        if not box_coords_mm:
            mediabox_mm = analysis.get("mediabox")
            if original_trimbox_mm and mediabox_mm:
                trim_width = abs(original_trimbox_mm["x1"] - original_trimbox_mm["x0"])
                trim_height = abs(original_trimbox_mm["y1"] - original_trimbox_mm["y0"])
                box_coords_mm = {
                    "x0": original_trimbox_mm["x0"],
                    "y0": original_trimbox_mm["y0"],
                    "x1": original_trimbox_mm["x0"] + trim_width,
                    "y1": original_trimbox_mm["y0"] + trim_height,
                }
            else:
                box_coords_mm = mediabox_mm

        box_coords = {
            "x0": box_coords_mm["x0"] * self.MM_TO_POINTS,
            "y0": box_coords_mm["y0"] * self.MM_TO_POINTS,
            "x1": box_coords_mm["x1"] * self.MM_TO_POINTS,
            "y1": box_coords_mm["y1"] * self.MM_TO_POINTS,
        }
        return box_coords_mm, box_coords

    def _get_winding_route(self, job_config: PDFJobConfig) -> int | None:
        """Compute winding route from job config."""
        if job_config.winding is None:
            return None
        try:
            return route_by_winding(job_config.winding)
        except Exception:
            try:
                return route_by_winding_str(str(job_config.winding))
            except Exception:
                return None

    def _build_success_response(
        self,
        job_config: PDFJobConfig,
        output_path: str,
        analysis: Dict[str, Any],
        winding_route: int | None,
        dimension_warnings: List[str],
        repair_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build successful processing response."""
        result = {
            "success": True,
            "message": f"Successfully processed PDF with {job_config.shape} shape",
            "reference": job_config.reference,
            "output_path": output_path,
            "analysis": analysis,
            "updated_job_config": job_config,
            "processing_details": {
                "shape_type": job_config.shape,
                "dimensions": f"{job_config.width}mm x {job_config.height}mm",
                "spot_color": job_config.spot_color_name,
                "line_thickness": job_config.line_thickness,
                "winding": job_config.winding,
                "winding_route": winding_route,
                "dimension_warnings": dimension_warnings,
                "pdf_repair": repair_info,
            },
        }
        if job_config.shape == ShapeType.rectangle:
            result["processing_details"]["corner_radius"] = f"{job_config.radius}mm"
        return result

    def process_batch(self, pdf_paths: list, job_configs: list) -> list:
        """Process multiple PDFs in batch."""
        return [
            self.process_pdf(pdf_path, job_config)
            for pdf_path, job_config in zip(pdf_paths, job_configs)
        ]
