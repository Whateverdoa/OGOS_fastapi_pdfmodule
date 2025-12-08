"""
Shape Processing Module

Handles processing of custom and standard (circle/rectangle) shapes.
Extracted from PDFProcessor for better organization.
"""

import os
import shutil
import tempfile
from typing import Any, Dict

from ..models.schemas import FontMode, PDFJobConfig, ShapeType
from ..utils.pdf_utils import PDFUtils
from ..utils.pymupdf_compound_path_tool import PyMuPDFCompoundPathTool
from ..utils.spot_color_handler import SpotColorHandler
from ..utils.spot_color_renamer import SpotColorRenamer
from ..utils.stans_compound_path_converter import StansCompoundPathConverter
from ..utils.universal_dieline_remover import UniversalDielineRemover
from .shape_generators import ShapeGenerator


class ShapeProcessor:
    """Processes PDF shapes (custom, circle, rectangle)."""

    def __init__(self):
        self.shape_generator = ShapeGenerator()
        self.spot_color_handler = SpotColorHandler()
        self.spot_color_renamer = SpotColorRenamer()
        self.pdf_utils = PDFUtils()
        self.dieline_remover = UniversalDielineRemover()
        self.compound_converter = StansCompoundPathConverter()
        self.pymupdf_compound_tool = PyMuPDFCompoundPathTool()

    def process_custom_shape(
        self, pdf_path: str, job_config: PDFJobConfig, analysis: Dict[str, Any]
    ) -> str:
        """Process custom shape - keep existing shape but rename spot color."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        output_path = temp_file.name
        temp_file.close()

        # Rename cutcontour to stans
        rename_temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        rename_temp_path = rename_temp.name
        rename_temp.close()

        rename_success = self.spot_color_renamer.rename_cutcontour_to_stans(
            pdf_path, rename_temp_path, job_config.spot_color_name
        )
        if not rename_success:
            shutil.copy2(pdf_path, rename_temp_path)

        # Ensure compound paths
        compound_temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        compound_temp_path = compound_temp.name
        compound_temp.close()

        compound_result = self.compound_converter.ensure_compound_paths(
            rename_temp_path, compound_temp_path
        )
        source_path = (
            compound_temp_path if compound_result.get("success") else rename_temp_path
        )

        # Final spot color rename
        success = self.spot_color_handler.rename_spot_color(
            source_path, output_path, job_config.spot_color_name
        )
        if success:
            self.spot_color_handler.update_spot_color_properties(
                output_path,
                output_path,
                job_config.spot_color_name,
                job_config.line_thickness,
            )

        # Post-processing
        self._apply_post_processing(output_path, job_config)
        return output_path

    def process_standard_shape(
        self,
        pdf_path: str,
        job_config: PDFJobConfig,
        analysis: Dict[str, Any],
        box_coords: Dict[str, float],
    ) -> str:
        """Process standard shapes (circle/rectangle)."""
        # Create clean PDF without existing dielines
        clean_path = self._create_clean_pdf(pdf_path, job_config, analysis)

        # Generate new dieline
        dieline_path = self._generate_dieline(job_config, analysis, box_coords)

        # Merge clean PDF with dieline
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

        # Finalize
        self.pymupdf_compound_tool.process(output_path, output_path)
        self._prune_spot_colors(output_path, job_config.spot_color_name)
        self._ensure_overprint(
            output_path, job_config.spot_color_name, job_config.line_thickness
        )
        self._apply_font_handling(output_path, job_config)

        return output_path

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

    def _apply_font_handling(self, output_path: str, job_config: PDFJobConfig):
        """Handle font embedding/outlining."""
        try:
            if getattr(job_config, "fonts", FontMode.embed) == FontMode.outline:
                self.pdf_utils.outline_all_fonts(output_path)
            else:
                ok = self.pdf_utils.embed_all_fonts(output_path)
                if (not ok) or self.pdf_utils.has_unembedded_fonts(output_path):
                    self.pdf_utils.outline_all_fonts(output_path)
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

