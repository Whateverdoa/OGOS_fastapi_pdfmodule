import os
import tempfile
from typing import Dict, Any, Optional
from ..models.schemas import PDFJobConfig, ShapeType
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
            # Step 1: Analyze the PDF
            analysis = self.analyzer.analyze_pdf(pdf_path)
            
            # Get the appropriate box coordinates (trimbox or mediabox)
            # Convert back to points for shape generation
            box_coords_mm = analysis.get('trimbox') or analysis.get('mediabox')
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

            # Step 2: Process based on shape type
            if job_config.shape == ShapeType.custom:
                # For custom shapes, keep the existing shape but rename spot color
                output_path = self._process_custom_shape(
                    pdf_path, job_config, analysis
                )
            else:
                # For circle and rectangle, remove old dieline and add new one
                output_path = self._process_standard_shape(
                    pdf_path, job_config, analysis, box_coords
                )
                
            # Step 3: Prepare response
            result = {
                'success': True,
                'message': f'Successfully processed PDF with {job_config.shape} shape',
                'reference': job_config.reference,
                'output_path': output_path,
                'analysis': analysis,
                'processing_details': {
                    'shape_type': job_config.shape,
                    'dimensions': f'{job_config.width}mm x {job_config.height}mm',
                    'spot_color': job_config.spot_color_name,
                    'line_thickness': job_config.line_thickness,
                    'winding': job_config.winding,
                    'winding_route': winding_route
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
        else:
            import shutil
            shutil.copy2(source_path, output_path)

        # Final PyMuPDF compound-path normalization (also enforces stans/magenta/0.5pt)
        self.pymupdf_compound_tool.process(output_path, output_path)

        for temp_path in (rename_temp_path, compound_temp_path):
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
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
            
        # Step 2: Generate new dieline shape
        if job_config.shape == ShapeType.circle:
            dieline_path = self.shape_generator.create_circle_dieline(
                job_config.width,
                job_config.height,
                box_coords,
                job_config.spot_color_name,
                job_config.line_thickness
            )
        else:  # rectangle
            dieline_path = self.shape_generator.create_rectangle_dieline(
                job_config.width,
                job_config.height,
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

        return output_path
        
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
