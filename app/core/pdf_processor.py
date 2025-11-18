import os
import tempfile
from typing import Dict, Any, Optional, Tuple, List
from ..models.schemas import PDFJobConfig, ShapeType, FontMode
from .pdf_analyzer import PDFAnalyzer
from .shape_generators import ShapeGenerator
from ..utils.spot_color_handler import SpotColorHandler
from ..utils.spot_color_renamer import SpotColorRenamer
from ..utils.pdf_utils import PDFUtils
from ..utils.universal_dieline_remover import UniversalDielineRemover
from ..utils.stans_compound_path_converter import StansCompoundPathConverter
from ..utils.pymupdf_compound_path_tool import PyMuPDFCompoundPathTool
from ..utils.winding_router import route_by_winding, route_by_winding_str


class PDFProcessor:
    """Main PDF processing orchestrator"""
    
    # Conversion constant: 1 mm = 2.83465 points
    MM_TO_POINTS = 2.83465
    
    def __init__(self):
        self.analyzer = PDFAnalyzer()
        self.shape_generator = ShapeGenerator()
        self.spot_color_handler = SpotColorHandler()
        self.spot_color_renamer = SpotColorRenamer()
        self.pdf_utils = PDFUtils()
        self.dieline_remover = UniversalDielineRemover()
        self.compound_converter = StansCompoundPathConverter()
        self.pymupdf_compound_tool = PyMuPDFCompoundPathTool()
        
    def process_pdf(self, pdf_path: str, job_config: PDFJobConfig) -> Dict[str, Any]:
        """
        Process a PDF according to the job configuration
        
        Args:
            pdf_path: Path to the input PDF
            job_config: Job configuration with shape and processing parameters
            
        Returns:
            Dictionary with processing results
        """
        try:
            # Optional rotation before any analysis/processing
            working_pdf_path = pdf_path
            if getattr(job_config, 'rotate_degrees', None) is not None:
                try:
                    deg = int(job_config.rotate_degrees)
                except Exception:
                    deg = 0
                if deg in (0, 90, 180, 270):
                    temp_rot = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                    temp_rot_path = temp_rot.name
                    temp_rot.close()
                    rotated = self.pdf_utils.rotate_pdf(pdf_path, temp_rot_path, deg)
                    if rotated:
                        working_pdf_path = temp_rot_path

            # Step 1: Analyze the PDF
            analysis = self.analyzer.analyze_pdf(working_pdf_path)
            original_trimbox_mm = analysis.get('trimbox')
            
            # Step 1.5: Pre-processing - dimension comparison and winding normalization
            working_pdf_path, job_config, analysis, dimension_warnings = self._preprocess_dimensions_and_winding(
                working_pdf_path, job_config, analysis
            )
            
            # Get the appropriate box coordinates (trimbox or mediabox)
            # Convert back to points for shape generation
            box_coords_mm = analysis.get('trimbox')
            if not box_coords_mm:
                mediabox_mm = analysis.get('mediabox')
                if original_trimbox_mm and mediabox_mm:
                    trim_width = abs(original_trimbox_mm['x1'] - original_trimbox_mm['x0'])
                    trim_height = abs(original_trimbox_mm['y1'] - original_trimbox_mm['y0'])
                    margin_x = original_trimbox_mm['x0']
                    margin_y = original_trimbox_mm['y0']
                    box_coords_mm = {
                        'x0': margin_x,
                        'y0': margin_y,
                        'x1': margin_x + trim_width,
                        'y1': margin_y + trim_height,
                    }
                else:
                    box_coords_mm = mediabox_mm
            box_coords = {
                'x0': box_coords_mm['x0'] * self.MM_TO_POINTS,
                'y0': box_coords_mm['y0'] * self.MM_TO_POINTS,
                'x1': box_coords_mm['x1'] * self.MM_TO_POINTS,
                'y1': box_coords_mm['y1'] * self.MM_TO_POINTS
            }
            
            # Compute winding route mapping if provided
            winding_route = None
            try:
                if job_config.winding is not None:
                    winding_route = route_by_winding(job_config.winding)
            except Exception:
                # Try string-based mapping as a fallback
                try:
                    winding_route = route_by_winding_str(str(job_config.winding))
                except Exception:
                    winding_route = None

            # Step 2: Validate trimbox matches job dimensions (after rotation/normalization)
            trimbox_validation_warnings = self._validate_trimbox_dimensions(
                box_coords_mm, job_config
            )
            dimension_warnings.extend(trimbox_validation_warnings)
            
            # Step 3: Process based on shape type
            if job_config.shape == ShapeType.custom:
                # For custom shapes, keep the existing shape but rename spot color
                output_path = self._process_custom_shape(
                    working_pdf_path, job_config, analysis
                )
            else:
                # For circle and rectangle, remove old dieline and add new one
                output_path = self._process_standard_shape(
                    working_pdf_path, job_config, analysis, box_coords
                )
                
            # Step 3: Prepare response
            result = {
                'success': True,
                'message': f'Successfully processed PDF with {job_config.shape} shape',
                'reference': job_config.reference,
                'output_path': output_path,
                'analysis': analysis,
                'updated_job_config': job_config,  # Include updated config for JSON normalization
                'processing_details': {
                    'shape_type': job_config.shape,
                    'dimensions': f'{job_config.width}mm x {job_config.height}mm',
                    'spot_color': job_config.spot_color_name,
                    'line_thickness': job_config.line_thickness,
                    'winding': job_config.winding,
                    'winding_route': winding_route,
                    'dimension_warnings': dimension_warnings
                }
            }
            
            if job_config.shape == ShapeType.rectangle:
                result['processing_details']['corner_radius'] = f'{job_config.radius}mm'
                
            return result
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Error processing PDF: {str(e)}',
                'reference': job_config.reference,
                'error': str(e)
            }
            
    def _process_custom_shape(
        self,
        pdf_path: str,
        job_config: PDFJobConfig,
        analysis: Dict[str, Any]
    ) -> str:
        """
        Process custom shape - keep existing shape but rename spot color
        """
        # Create output file
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        output_path = temp_file.name
        temp_file.close()
        
        rename_temp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        rename_temp_path = rename_temp.name
        rename_temp.close()

        rename_success = self.spot_color_renamer.rename_cutcontour_to_stans(
            pdf_path,
            rename_temp_path,
            job_config.spot_color_name
        )

        if not rename_success:
            import shutil
            shutil.copy2(pdf_path, rename_temp_path)

        compound_temp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        compound_temp_path = compound_temp.name
        compound_temp.close()

        compound_result = self.compound_converter.ensure_compound_paths(
            rename_temp_path,
            compound_temp_path
        )

        source_path = compound_temp_path if compound_result.get('success') else rename_temp_path

        # Final pass to ensure the spot color resource name matches exactly
        success = self.spot_color_handler.rename_spot_color(
            source_path,
            output_path,
            job_config.spot_color_name
        )

        if success:
            # Update spot color properties (ensure 100% magenta, overprint)
            self.spot_color_handler.update_spot_color_properties(
                output_path,
                output_path,
                job_config.spot_color_name,
                job_config.line_thickness
            )
        
        # Optional: remove registration/crop marks (Separation/All)
        if getattr(job_config, 'remove_marks', False):
            temp_markless = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            markless_path = temp_markless.name
            temp_markless.close()
            mark_res = self.dieline_remover.remove_registration_marks(output_path, markless_path)
            if mark_res.get('success'):
                try:
                    os.replace(markless_path, output_path)
                except Exception:
                    pass

        # Best-effort: font handling per job config with fallback to outline
        try:
            if getattr(job_config, 'fonts', FontMode.embed) == FontMode.outline:
                self.pdf_utils.outline_all_fonts(output_path)
            else:
                ok = self.pdf_utils.embed_all_fonts(output_path)
                # If embedding failed or fonts still not embedded, fallback to outline
                if (not ok) or self.pdf_utils.has_unembedded_fonts(output_path):
                    self.pdf_utils.outline_all_fonts(output_path)
        except Exception:
            pass

        return output_path
        
    def _process_standard_shape(
        self,
        pdf_path: str,
        job_config: PDFJobConfig,
        analysis: Dict[str, Any],
        box_coords: Dict[str, float]
    ) -> str:
        """
        Process standard shapes (circle/rectangle) - remove old and add new dieline
        """
        # Step 1: Create a clean version without dielines
        temp_clean = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        clean_path = temp_clean.name
        temp_clean.close()
        
        if analysis.get('has_cutcontour') or len(analysis.get('spot_colors', [])) > 0:
            # Remove existing dielines using Universal Dieline Remover
            removal_result = self.dieline_remover.remove_dielines_from_shapes(
                pdf_path, clean_path, job_config.shape.value
            )
            if not removal_result.get('success'):
                # Fallback to old method
                self.spot_color_handler.remove_dieline_paths(pdf_path, clean_path)
        else:
            # Just copy if no dielines present
            import shutil
            shutil.copy2(pdf_path, clean_path)
        
        # Optional: remove registration/crop marks (Separation/All)
        if getattr(job_config, 'remove_marks', False):
            temp_markless = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            markless_path = temp_markless.name
            temp_markless.close()
            mark_res = self.dieline_remover.remove_registration_marks(clean_path, markless_path)
            if mark_res.get('success'):
                try:
                    os.unlink(clean_path)
                except Exception:
                    pass
                clean_path = markless_path

        # Rotation is now handled in the pre-processing step

        # Step 2: Generate new dieline shape using the current trimbox dimensions
        box_coords_mm = analysis.get('trimbox') or analysis.get('mediabox')
        if not box_coords_mm:
            raise ValueError("No trimbox or mediabox available for dieline placement")
        dieline_width_mm = abs(float(box_coords_mm['x1']) - float(box_coords_mm['x0']))
        dieline_height_mm = abs(float(box_coords_mm['y1']) - float(box_coords_mm['y0']))
        
        if job_config.shape == ShapeType.circle:
            dieline_path = self.shape_generator.create_circle_dieline(
                dieline_width_mm,
                dieline_height_mm,
                box_coords,
                job_config.spot_color_name,
                job_config.line_thickness
            )
        else:  # rectangle
            dieline_path = self.shape_generator.create_rectangle_dieline(
                dieline_width_mm,
                dieline_height_mm,
                job_config.radius,
                box_coords,
                job_config.spot_color_name,
                job_config.line_thickness
            )
            
        # Step 3: Merge the clean PDF with the new dieline
        temp_output = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        output_path = temp_output.name
        temp_output.close()
        
        success = self.pdf_utils.merge_pdfs(clean_path, dieline_path, output_path)

        # Clean up temporary files
        try:
            os.unlink(clean_path)
            os.unlink(dieline_path)
        except:
            pass
        
        # Normalize dieline compound path and enforce stroke properties
        self.pymupdf_compound_tool.process(output_path, output_path)
        
        # Post-merge pruning: remove any leftover dieline spot colors except desired one
        try:
            pruned_output = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False).name
            self.dieline_remover.prune_unwanted_spot_colors(
                output_path,
                pruned_output,
                allowed_names={job_config.spot_color_name}
            )
            # Replace output with pruned version
            os.replace(pruned_output, output_path)
        except Exception:
            # Non-fatal: keep unpruned output
            pass

        # Ensure overprint is enabled for the new dieline spot
        try:
            self.pdf_utils.ensure_overprint_for_spot(output_path, job_config.spot_color_name)
        except Exception:
            pass

        # Embed/Outline fonts in the final PDF (best-effort with fallback)
        try:
            if getattr(job_config, 'fonts', FontMode.embed) == FontMode.outline:
                self.pdf_utils.outline_all_fonts(output_path)
            else:
                ok = self.pdf_utils.embed_all_fonts(output_path)
                if (not ok) or self.pdf_utils.has_unembedded_fonts(output_path):
                    self.pdf_utils.outline_all_fonts(output_path)
        except Exception:
            pass

        return output_path
    
    def _preprocess_dimensions_and_winding(
        self, 
        pdf_path: str, 
        job_config: PDFJobConfig, 
        analysis: Dict[str, Any]
    ) -> Tuple[str, PDFJobConfig, Dict[str, Any], List[str]]:
        """
        Pre-process PDF to handle dimension comparison and winding normalization.
        
        Returns:
            Tuple of (updated_pdf_path, updated_job_config, updated_analysis, warnings)
        """
        warnings = []
        working_pdf_path = pdf_path
        
        # Get artwork dimensions from trimbox or mediabox
        box_coords_mm = analysis.get('trimbox') or analysis.get('mediabox')
        if not box_coords_mm:
            warnings.append("No trimbox or mediabox found in PDF")
            return working_pdf_path, job_config, analysis, warnings
            
        artwork_width = abs(box_coords_mm['x1'] - box_coords_mm['x0'])
        artwork_height = abs(box_coords_mm['y1'] - box_coords_mm['y0'])
        
        # Compare with order dimensions (tolerance of 1mm)
        tolerance = 1.0
        order_width = float(job_config.width)
        order_height = float(job_config.height)
        
        width_matches = abs(artwork_width - order_width) <= tolerance
        height_matches = abs(artwork_height - order_height) <= tolerance
        
        # Check if dimensions match in swapped orientation
        width_matches_swapped = abs(artwork_width - order_height) <= tolerance
        height_matches_swapped = abs(artwork_height - order_width) <= tolerance
        
        dimensions_match = width_matches and height_matches
        dimensions_match_swapped = width_matches_swapped and height_matches_swapped
        
        # Handle rotation logic - check for rotate_degrees from ZIP pipeline or winding
        current_winding = getattr(job_config, 'winding', None)
        rotate_degrees = getattr(job_config, 'rotate_degrees', None)
        
        # Determine rotation angle
        rotation_angle = None
        if rotate_degrees is not None:
            # ZIP pipeline already determined rotation
            rotation_angle = rotate_degrees
            warnings.append(f"Using rotation from ZIP pipeline: {rotation_angle}°")
        elif current_winding is not None and current_winding != 2:
            # Direct winding processing
            try:
                rotation_angle = route_by_winding(current_winding)
                warnings.append(f"Calculated rotation from winding {current_winding}: {rotation_angle}°")
            except Exception as e:
                warnings.append(f"Error calculating rotation from winding {current_winding}: {str(e)}")
        
        # Apply rotation if needed
        if rotation_angle and rotation_angle % 360 != 0:
            # Create rotated PDF
            temp_rot = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_rot_path = temp_rot.name
            temp_rot.close()
            
            if self.pdf_utils.rotate_pdf(pdf_path, temp_rot_path, rotation_angle, flatten=True):
                working_pdf_path = temp_rot_path
                
                # Re-analyze the rotated PDF to get flattened dimensions
                analysis = self.analyzer.analyze_pdf(working_pdf_path)
                
                # Update job config dimensions to match the flattened PDF
                box_coords_mm = analysis.get('trimbox') or analysis.get('mediabox')
                if box_coords_mm:
                    actual_width = abs(box_coords_mm['x1'] - box_coords_mm['x0'])
                    actual_height = abs(box_coords_mm['y1'] - box_coords_mm['y0'])
                    job_config.width = actual_width
                    job_config.height = actual_height
                    warnings.append(f"Rotated artwork {rotation_angle}° and updated dimensions to {actual_width:.1f}x{actual_height:.1f}mm")
                else:
                    warnings.append(f"Rotated artwork {rotation_angle}°")

                # Normalize winding to 2
                job_config.winding = 2
                warnings.append("Normalized winding to 2")
            else:
                warnings.append(f"Failed to rotate PDF by {rotation_angle}°")
        
        # Check dimension match after any rotation or normalization
        if not rotation_angle:
            if not dimensions_match:
                if dimensions_match_swapped:
                    warnings.append(
                        f"Artwork dimensions ({artwork_width:.1f}x{artwork_height:.1f}mm) are swapped compared to "
                        f"order ({order_width:.1f}x{order_height:.1f}mm)"
                    )
                else:
                    warnings.append(
                        f"Artwork dimensions ({artwork_width:.1f}x{artwork_height:.1f}mm) don't match "
                        f"order ({order_width:.1f}x{order_height:.1f}mm)"
                    )
        
        return working_pdf_path, job_config, analysis, warnings
    
    def _validate_trimbox_dimensions(
        self, 
        box_coords_mm: Dict[str, float], 
        job_config: PDFJobConfig
    ) -> List[str]:
        """
        Validate that trimbox dimensions match job config dimensions after rotation/normalization.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        if not box_coords_mm:
            warnings.append("No trimbox found for dimension validation")
            return warnings
            
        trimbox_width = abs(box_coords_mm['x1'] - box_coords_mm['x0'])
        trimbox_height = abs(box_coords_mm['y1'] - box_coords_mm['y0'])
        
        order_width = float(job_config.width)
        order_height = float(job_config.height)
        
        tolerance = 1.0  # 1mm tolerance
        
        width_matches = abs(trimbox_width - order_width) <= tolerance
        height_matches = abs(trimbox_height - order_height) <= tolerance
        
        if not (width_matches and height_matches):
            warnings.append(
                f"Trimbox dimensions ({trimbox_width:.1f}x{trimbox_height:.1f}mm) "
                f"don't match order dimensions ({order_width:.1f}x{order_height:.1f}mm) "
                f"after rotation/normalization. Stans placement may be incorrect."
            )
        
        return warnings
        
    def process_batch(self, pdf_paths: list, job_configs: list) -> list:
        """
        Process multiple PDFs in batch
        
        Args:
            pdf_paths: List of PDF file paths
            job_configs: List of job configurations
            
        Returns:
            List of processing results
        """
        results = []
        
        for pdf_path, job_config in zip(pdf_paths, job_configs):
            result = self.process_pdf(pdf_path, job_config)
            results.append(result)
            
        return results
