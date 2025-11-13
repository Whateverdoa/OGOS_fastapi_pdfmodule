from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import CMYKColorSep
from typing import Dict, Tuple, Optional
import os
import tempfile
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, NumberObject, BooleanObject


class ShapeGenerator:
    """Generates PDF shapes (circle, rectangle) with spot color dielines"""
    
    def __init__(self):
        self.default_spot_color = "stans"
        self.default_line_thickness = 0.5  # points
        
    def create_circle_dieline(
        self,
        width_mm: float,
        height_mm: float,
        box_coords: Dict[str, float],
        spot_color_name: str = None,
        line_thickness: float = None
    ) -> str:
        """
        Create a PDF with a circular/oval dieline positioned on the trimbox
        
        Args:
            width_mm: Width in millimeters
            height_mm: Height in millimeters
            box_coords: Trimbox coordinates in points
            spot_color_name: Name for the spot color
            line_thickness: Line thickness in points
            
        Returns:
            Path to the generated PDF file
        """
        spot_color_name = spot_color_name or self.default_spot_color
        line_thickness = line_thickness or self.default_line_thickness
        
        # Convert dimensions to points
        width_pt = width_mm * mm
        height_pt = height_mm * mm
        
        # Use the full page size for the canvas (including margins)
        # but position the shape on the trimbox area
        page_width = box_coords['x1'] - box_coords['x0']
        page_height = box_coords['y1'] - box_coords['y0']
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        # Create canvas with the same size as original PDF page
        c = canvas.Canvas(temp_path, pagesize=(page_width + 2*box_coords['x0'], page_height + 2*box_coords['y0']))
        
        # Define spot color (100% Magenta with overprint)
        stans_color = CMYKColorSep(
            spotName=spot_color_name,
            density=1.0,
            cyan=0,
            magenta=1,
            yellow=0,
            black=0
        )
        
        # Set drawing properties for the new dieline
        c.setStrokeColor(stans_color)
        c.setFillColorCMYK(0, 0, 0, 0, alpha=0)  # Transparent fill
        c.setLineWidth(line_thickness)
        
        # Position in trimbox center
        trimbox_center_x = box_coords['x0'] + page_width / 2
        trimbox_center_y = box_coords['y0'] + page_height / 2
        
        # Draw ellipse (or circle if width == height) in trimbox center
        c.ellipse(
            trimbox_center_x - width_pt/2,
            trimbox_center_y - height_pt/2,
            trimbox_center_x + width_pt/2,
            trimbox_center_y + height_pt/2,
            stroke=1,
            fill=0
        )
        
        # Save PDF
        c.save()

        # Ensure overprint is enabled in the generated PDF
        self._apply_overprint_to_pdf(temp_path)

        return temp_path
        
    def create_rectangle_dieline(
        self,
        width_mm: float,
        height_mm: float,
        corner_radius_mm: float,
        box_coords: Dict[str, float],
        spot_color_name: str = None,
        line_thickness: float = None
    ) -> str:
        """
        Create a PDF with a rectangular dieline positioned on the trimbox
        
        Args:
            width_mm: Width in millimeters
            height_mm: Height in millimeters
            corner_radius_mm: Corner radius in millimeters
            box_coords: Trimbox coordinates in points
            spot_color_name: Name for the spot color
            line_thickness: Line thickness in points
            
        Returns:
            Path to the generated PDF file
        """
        spot_color_name = spot_color_name or self.default_spot_color
        line_thickness = line_thickness or self.default_line_thickness
        
        # Convert dimensions to points
        width_pt = width_mm * mm
        height_pt = height_mm * mm
        radius_pt = corner_radius_mm * mm
        
        # Validate radius
        max_radius = min(width_pt / 2, height_pt / 2)
        if radius_pt > max_radius:
            radius_pt = max_radius
            
        # Use the full page size for the canvas (including margins)
        page_width = box_coords['x1'] - box_coords['x0']
        page_height = box_coords['y1'] - box_coords['y0']
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        # Create canvas with the same size as original PDF page
        c = canvas.Canvas(temp_path, pagesize=(page_width + 2*box_coords['x0'], page_height + 2*box_coords['y0']))
        
        # Define spot color (100% Magenta with overprint)
        stans_color = CMYKColorSep(
            spotName=spot_color_name,
            density=1.0,
            cyan=0,
            magenta=1,
            yellow=0,
            black=0
        )
        
        # Set drawing properties for the new dieline
        c.setStrokeColor(stans_color)
        c.setFillColorCMYK(0, 0, 0, 0, alpha=0)  # Transparent fill
        c.setLineWidth(line_thickness)
        
        # Position in trimbox center
        trimbox_center_x = box_coords['x0'] + page_width / 2
        trimbox_center_y = box_coords['y0'] + page_height / 2
        
        # Calculate rectangle position (centered in trimbox)
        x = trimbox_center_x - width_pt / 2
        y = trimbox_center_y - height_pt / 2
        
        # Draw rounded rectangle in trimbox center
        c.roundRect(x, y, width_pt, height_pt, radius_pt, stroke=1, fill=0)
        
        # Save PDF
        c.save()

        # Ensure overprint is enabled in the generated PDF
        self._apply_overprint_to_pdf(temp_path)

        return temp_path
        
    def create_stepped_dieline(
        self,
        width_mm: float,
        height_mm: float,
        shape_type: str,
        corner_radius_mm: float,
        box_coords: Dict[str, float],
        step_x: int = 1,
        step_y: int = 1,
        space_x_mm: float = 0,
        space_y_mm: float = 0,
        spot_color_name: str = None,
        line_thickness: float = None
    ) -> str:
        """
        Create a PDF with stepped/repeated dielines
        
        Args:
            width_mm: Width of single shape in millimeters
            height_mm: Height of single shape in millimeters
            shape_type: "circle" or "rectangle"
            corner_radius_mm: Corner radius for rectangles
            box_coords: Trimbox or mediabox coordinates
            step_x: Number of repetitions horizontally
            step_y: Number of repetitions vertically
            space_x_mm: Horizontal spacing between shapes
            space_y_mm: Vertical spacing between shapes
            spot_color_name: Name for the spot color
            line_thickness: Line thickness in points
            
        Returns:
            Path to the generated PDF file
        """
        spot_color_name = spot_color_name or self.default_spot_color
        line_thickness = line_thickness or self.default_line_thickness
        
        # Convert dimensions to points
        width_pt = width_mm * mm
        height_pt = height_mm * mm
        radius_pt = corner_radius_mm * mm
        space_x_pt = space_x_mm * mm
        space_y_pt = space_y_mm * mm
        
        # Calculate page size from box coordinates
        page_width = box_coords['x1'] - box_coords['x0']
        page_height = box_coords['y1'] - box_coords['y0']
        
        # Calculate total content size
        total_width = (step_x * width_pt) + (max(0, step_x - 1) * space_x_pt)
        total_height = (step_y * height_pt) + (max(0, step_y - 1) * space_y_pt)
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        # Create canvas
        c = canvas.Canvas(temp_path, pagesize=(page_width, page_height))
        
        # Define spot color
        stans_color = CMYKColorSep(
            spotName=spot_color_name,
            density=1.0,
            cyan=0,
            magenta=1,
            yellow=0,
            black=0
        )
        
        # Set drawing properties
        c.setStrokeColor(stans_color)
        c.setFillColorCMYK(0, 0, 0, 0, alpha=0)
        c.setLineWidth(line_thickness)
        
        # Calculate starting position (centered)
        start_x = (page_width - total_width) / 2
        start_y = (page_height - total_height) / 2
        
        # Draw shapes
        for j in range(step_y):
            for i in range(step_x):
                x = start_x + i * (width_pt + space_x_pt)
                y = start_y + j * (height_pt + space_y_pt)
                
                if shape_type == "circle":
                    c.ellipse(
                        x, y,
                        x + width_pt, y + height_pt,
                        stroke=1, fill=0
                    )
                else:  # rectangle
                    c.roundRect(x, y, width_pt, height_pt, radius_pt, stroke=1, fill=0)
                    
        c.save()
        # Ensure overprint is enabled in the generated PDF
        self._apply_overprint_to_pdf(temp_path)
        return temp_path

    def _apply_overprint_to_pdf(self, pdf_path: str):
        """
        Add an ExtGState with stroke/fill overprint enabled and apply it
        to the page content by inserting a 'gs' at the start of the stream.
        """
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()

            page = reader.pages[0]
            resources = page.get('/Resources')
            if resources is None:
                resources = DictionaryObject()
                page[NameObject('/Resources')] = resources
            elif hasattr(resources, 'get_object'):
                resources = resources.get_object()

            # Prepare ExtGState dictionary
            extg = resources.get('/ExtGState')
            if extg is None:
                extg = DictionaryObject()
                resources[NameObject('/ExtGState')] = extg
            elif hasattr(extg, 'get_object'):
                extg = extg.get_object()

            gs_dict = DictionaryObject()
            gs_dict.update({
                NameObject('/Type'): NameObject('/ExtGState'),
                NameObject('/OP'): BooleanObject(True),  # stroke overprint
                NameObject('/op'): BooleanObject(True),  # fill overprint
                NameObject('/OPM'): NumberObject(1),
            })

            gs_ref = writer._add_object(gs_dict)
            extg[NameObject('/GSop')] = gs_ref

            # Insert '/GSop gs' at start of the first content stream
            contents = page.get('/Contents')
            if hasattr(contents, 'get_object'):
                contents = contents.get_object()

            def inject(stream_obj):
                if hasattr(stream_obj, 'get_object'):
                    stream_obj = stream_obj.get_object()
                if hasattr(stream_obj, 'get_data') and hasattr(stream_obj, 'set_data'):
                    try:
                        data = stream_obj.get_data()
                    except Exception:
                        data = b''
                    patched = b"/GSop gs\n" + data
                    stream_obj.set_data(patched)

            if contents is not None:
                if isinstance(contents, list):
                    if contents:
                        inject(contents[0])
                else:
                    inject(contents)

            writer.add_page(page)
            with open(pdf_path, 'wb') as f:
                writer.write(f)
        except Exception:
            # Non-fatal: leave PDF as-is
            pass
