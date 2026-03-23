"""
Shape Processing Module

Handles processing of custom and standard (circle/rectangle) shapes.
Extracted from PDFProcessor for better organization.

Pipeline per spec:
1. Font check/fix first
2. Shape detection (circle/rectangle vs custom)
3. Custom shapes use StansProcessor V3
4. Rotation applied based on winding
"""

import logging
import os
import shutil
import tempfile
from typing import Any, Dict

from ..models.schemas import FontMode, PDFJobConfig, ShapeType
from ..utils.pdf_utils import PDFUtils
from ..utils.spot_color_handler import SpotColorHandler
from ..utils.spot_color_renamer import SpotColorRenamer
from ..utils.stans_processor_v3 import StansProcessor
from ..utils.universal_dieline_remover import UniversalDielineRemover
from .shape_generators import ShapeGenerator

logger = logging.getLogger(__name__)


class ShapeProcessor:
    """Processes PDF shapes (custom, circle, rectangle)."""

    def __init__(self):
        self.shape_generator = ShapeGenerator()
        self.spot_color_handler = SpotColorHandler()
        self.spot_color_renamer = SpotColorRenamer()
        self.pdf_utils = PDFUtils()
        self.dieline_remover = UniversalDielineRemover()
        # V3 processor for custom shapes
        self.stans_processor = StansProcessor()

    def process_custom_shape(
        self, pdf_path: str, job_config: PDFJobConfig, analysis: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Process custom shape using StansProcessor V3.
        
        Pipeline:
        1. Check and fix fonts (if needed)
        2. Use V3 processor for compound path creation
        3. Apply rotation based on winding
        """
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        output_path = temp_file.name
        temp_file.close()

        # Step 1: Font check/fix FIRST
        working_path = self._ensure_fonts(pdf_path, job_config)
        
        # Step 2: Use StansProcessor V3 for compound path
        processor = StansProcessor(
            spot_color_name=job_config.spot_color_name,
            line_thickness=job_config.line_thickness,
            winding=job_config.winding or 2
        )
        
        result = processor.process(working_path, output_path)
        
        if not result.success:
            # Fallback: copy original if V3 fails
            logger.warning(f"V3 processor failed: {result.error}, using original")
            shutil.copy2(pdf_path, output_path)
        
        # Post-processing (marks removal if needed)
        self._apply_post_processing(output_path, job_config)
        
        stats = {
            "original_stans_count": result.original_stans_count,
            "compound_paths_created": result.compound_paths_created,
            "rotation_applied": result.rotation_applied,
            "colors_renamed": result.colors_renamed,
            "font_fixed": getattr(result, 'font_fixed', False),
        }
        return output_path, stats
    
    def _ensure_fonts(self, pdf_path: str, job_config: PDFJobConfig) -> str:
        """
        Check and fix fonts before processing.
        Returns path to working file (may be original or temp with fixed fonts).
        """
        # Check for font issues
        if not PDFUtils.has_unembedded_fonts(pdf_path):
            return pdf_path
        
        logger.info("Detected unembedded fonts, attempting to fix")
        
        # Create temp copy for font fixing
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_path = temp_file.name
        temp_file.close()
        shutil.copy2(pdf_path, temp_path)
        
        # Try embedding first, then outlining as fallback
        font_mode = getattr(job_config, 'font_mode', None)
        
        if font_mode == FontMode.outline:
            if PDFUtils.outline_all_fonts(temp_path):
                logger.info("Fonts outlined successfully")
                return temp_path
        else:
            if PDFUtils.embed_all_fonts(temp_path):
                logger.info("Fonts embedded successfully")
                return temp_path
            # Fallback to outline
            if PDFUtils.outline_all_fonts(temp_path):
                logger.info("Fonts outlined as fallback")
                return temp_path
        
        logger.warning("Font fixing failed, using original")
        os.unlink(temp_path)
        return pdf_path


    def process_standard_shape(
        self,
        pdf_path: str,
        job_config: PDFJobConfig,
        analysis: Dict[str, Any],
        box_coords: Dict[str, float],
    ) -> tuple[str, Dict[str, Any]]:
        """Process standard shapes (circle/rectangle)."""
        # Step 1: Font check/fix FIRST
        working_path = self._ensure_fonts(pdf_path, job_config)

        # Create clean PDF without existing dielines
        clean_path = self._create_clean_pdf(working_path, job_config, analysis)

        # Step 2: Apply font handling to clean PDF BEFORE merging stans
        # This prevents Ghostscript from reordering the stans into wrong position
        self._apply_font_handling(clean_path, job_config)

        # Generate new dieline
        dieline_path = self._generate_dieline(job_config, analysis, box_coords)

        # Merge clean PDF with dieline (stans stays on top, outside transforms)
        temp_output = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        output_path = temp_output.name
        temp_output.close()

        self.pdf_utils.merge_pdfs(clean_path, dieline_path, output_path)

        # Cleanup temp files
        for path in (clean_path, dieline_path):
            try:
                os.unlink(path)
            except Exception:
                pass

        # Finalize: prune spot colors and ensure overprint
        # No compound path processing needed - we just generated a single new shape
        self._prune_spot_colors(output_path, job_config.spot_color_name)
        self._ensure_overprint(
            output_path, job_config.spot_color_name, job_config.line_thickness
        )
        # Apply remaining post-processing (marks removal, q/Q fix) but NOT font handling again
        self._apply_post_processing_no_fonts(output_path, job_config)

        stats = {
            "original_stans_count": 0,  # We removed existing, created new
            "compound_paths_created": 1,  # We created one new shape
            "shape_generated": job_config.shape.value,
        }
        return output_path, stats

    def _create_clean_pdf(
        self, pdf_path: str, job_config: PDFJobConfig, analysis: Dict[str, Any]
    ) -> str:
        """Create a clean PDF without existing dielines."""
        temp_clean = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        clean_path = temp_clean.name
        temp_clean.close()

        if analysis.get("has_cutcontour") or len(analysis.get("spot_colors", [])) > 0:
            removal_result = self.dieline_remover.remove_dielines_from_shapes(
                pdf_path, clean_path, job_config.shape.value
            )
            if not removal_result.get("success"):
                self.spot_color_handler.remove_dieline_paths(pdf_path, clean_path)
        else:
            shutil.copy2(pdf_path, clean_path)

        # Remove marks if requested
        if getattr(job_config, "remove_marks", False):
            temp_markless = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            markless_path = temp_markless.name
            temp_markless.close()
            mark_res = self.dieline_remover.remove_registration_marks(
                clean_path, markless_path
            )
            if mark_res.get("success"):
                try:
                    os.unlink(clean_path)
                except Exception:
                    pass
                clean_path = markless_path

        return clean_path

    def _generate_dieline(
        self,
        job_config: PDFJobConfig,
        analysis: Dict[str, Any],
        box_coords: Dict[str, float],
    ) -> str:
        """Generate new dieline shape."""
        box_coords_mm = analysis.get("trimbox") or analysis.get("mediabox")
        if not box_coords_mm:
            raise ValueError("No trimbox or mediabox available for dieline placement")

        width_mm = abs(float(box_coords_mm["x1"]) - float(box_coords_mm["x0"]))
        height_mm = abs(float(box_coords_mm["y1"]) - float(box_coords_mm["y0"]))

        if job_config.shape == ShapeType.circle:
            return self.shape_generator.create_circle_dieline(
                width_mm,
                height_mm,
                box_coords,
                job_config.spot_color_name,
                job_config.line_thickness,
            )
        else:
            return self.shape_generator.create_rectangle_dieline(
                width_mm,
                height_mm,
                job_config.radius,
                box_coords,
                job_config.spot_color_name,
                job_config.line_thickness,
            )

    def _apply_post_processing(self, output_path: str, job_config: PDFJobConfig):
        """Apply post-processing: marks removal and font handling."""
        logger = logging.getLogger(__name__)
        logger.info(f"Starting post-processing for {output_path}")

        if getattr(job_config, "remove_marks", False):
            temp_markless = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            markless_path = temp_markless.name
            temp_markless.close()
            mark_res = self.dieline_remover.remove_registration_marks(
                output_path, markless_path
            )
            if mark_res.get("success"):
                try:
                    os.replace(markless_path, output_path)
                except Exception:
                    pass

        self._apply_font_handling(output_path, job_config)

        # Always fix operator imbalances (q/Q, BT/ET, BMC/EMC) as final cleanup
        try:
            logger.info(f"Fixing operator imbalances in {output_path}")
            from app.utils.q_Q_fixer import fix_q_Q_imbalance
            fix_result = fix_q_Q_imbalance(output_path)
            logger.info(f"Operator fix result: {fix_result}")
        except Exception as e:
            logger.error(f"Failed to fix operators: {e}", exc_info=True)

    def _apply_post_processing_no_fonts(self, output_path: str, job_config: PDFJobConfig):
        """Apply post-processing WITHOUT font handling (for standard shapes where fonts are handled before merge)."""
        logger = logging.getLogger(__name__)
        logger.info(f"Starting post-processing (no fonts) for {output_path}")

        if getattr(job_config, "remove_marks", False):
            temp_markless = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            markless_path = temp_markless.name
            temp_markless.close()
            mark_res = self.dieline_remover.remove_registration_marks(
                output_path, markless_path
            )
            if mark_res.get("success"):
                try:
                    os.replace(markless_path, output_path)
                except Exception:
                    pass

        # Skip font handling - already done before merge

        # Always fix operator imbalances (q/Q, BT/ET, BMC/EMC) as final cleanup
        try:
            logger.info(f"Fixing operator imbalances in {output_path}")
            from app.utils.q_Q_fixer import fix_q_Q_imbalance
            fix_result = fix_q_Q_imbalance(output_path)
            logger.info(f"Operator fix result: {fix_result}")
        except Exception as e:
            logger.error(f"Failed to fix operators: {e}", exc_info=True)

    def _apply_font_handling(self, output_path: str, job_config: PDFJobConfig):
        """Handle font embedding/outlining and finalize for strict preflight checks."""
        try:
            if getattr(job_config, "fonts", FontMode.embed) == FontMode.outline:
                self.pdf_utils.outline_all_fonts(output_path)
            else:
                ok = self.pdf_utils.embed_all_fonts(output_path)
                if (not ok) or self.pdf_utils.has_unembedded_fonts(output_path):
                    self.pdf_utils.outline_all_fonts(output_path)

            # Final cleanup pass: some preflight tools flag stale font objects
            # even after successful embed/outline.
            self.pdf_utils.rewrite_preflight_safe(output_path)
        except Exception:
            pass

    def _prune_spot_colors(self, output_path: str, allowed_name: str):
        """Remove unwanted spot colors from output."""
        try:
            pruned = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
            self.dieline_remover.prune_unwanted_spot_colors(
                output_path, pruned, allowed_names={allowed_name}
            )
            os.replace(pruned, output_path)
        except Exception:
            pass

    def _ensure_overprint(self, output_path: str, spot_name: str, line_thickness: float = 0.5):
        """Ensure overprint is enabled for the dieline spot only.

        Uses SpotColorHandler.update_spot_color_properties for content-stream
        level overprint enforcement on stans strokes, then falls back to
        ensure_overprint_for_spot for Form XObjects that explicitly use the spot.
        """
        try:
            # Content-stream level: inject overprint GS before stans strokes
            self.spot_color_handler.update_spot_color_properties(
                output_path, output_path, spot_name, line_thickness
            )
            # Form XObject level: patch forms that explicitly reference the spot
            self.pdf_utils.ensure_overprint_for_spot(output_path, spot_name)
        except Exception:
            pass

