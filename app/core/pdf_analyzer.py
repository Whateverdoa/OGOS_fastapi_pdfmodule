import fitz  # PyMuPDF
from pypdf import PdfReader
from typing import Dict, List, Any, Optional, Tuple, Set
import os


class PDFAnalyzer:
    """Analyzes PDF files to extract dimensions, trimbox, and dieline information"""
    
    # Conversion constant: 1 point = 0.352778 mm
    POINTS_TO_MM = 0.352778
    
    # Target spot colors for dieline detection
    TARGET_SPOT_COLORS = [
        'CutContour', 'KissCut', 'Kiss Cut', 'Cut Contour',
        'cutcontour', 'kisscut', 'kiss cut', 'cut contour',
        'CUTCONTOUR', 'KISSCUT', 'CUT CONTOUR', 'KISS CUT',
        'stans', 'Stans', 'STANS',  # Dutch for dieline
        'DieCut', 'diecut', 'DIECUT', 'Die Cut', 'die cut', 'DIE CUT'
    ]

    DIELINE_LAYER_KEYWORDS = {
        value.replace(' ', '').replace('_', '').lower()
        for value in TARGET_SPOT_COLORS
    }
    
    def __init__(self):
        self.doc = None
        self.reader = None
        
    def analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Analyze a PDF file and extract relevant information
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing analysis results
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        try:
            # Open with both PyMuPDF and pypdf for comprehensive analysis
            self.doc = fitz.open(pdf_path)
            self.reader = PdfReader(pdf_path)
            
            # Get first page for analysis (assuming single page for labels)
            first_page = self.doc[0]
            
            # Extract basic information (convert to mm)
            pdf_size = {
                "width": round(first_page.rect.width * self.POINTS_TO_MM, 2),
                "height": round(first_page.rect.height * self.POINTS_TO_MM, 2)
            }
            
            # Get mediabox (convert to mm)
            mediabox = {
                "x0": round(first_page.mediabox.x0 * self.POINTS_TO_MM, 2),
                "y0": round(first_page.mediabox.y0 * self.POINTS_TO_MM, 2),
                "x1": round(first_page.mediabox.x1 * self.POINTS_TO_MM, 2),
                "y1": round(first_page.mediabox.y1 * self.POINTS_TO_MM, 2)
            }
            
            # Get trimbox if present (convert to mm)
            trimbox = None
            if first_page.trimbox != first_page.mediabox:
                trimbox = {
                    "x0": round(first_page.trimbox.x0 * self.POINTS_TO_MM, 2),
                    "y0": round(first_page.trimbox.y0 * self.POINTS_TO_MM, 2),
                    "x1": round(first_page.trimbox.x1 * self.POINTS_TO_MM, 2),
                    "y1": round(first_page.trimbox.y1 * self.POINTS_TO_MM, 2)
                }
            
            # Detect dielines and spot colors
            detected_dielines = self._detect_dielines(first_page)
            layer_report = self._collect_layered_dielines(first_page)
            spot_colors = self._extract_spot_colors()

            # Check if any target colors are present
            has_cutcontour = any(
                self._is_target_color(color) for color in spot_colors
            )

            return {
                "pdf_size": pdf_size,
                "page_count": len(self.doc),
                "mediabox": mediabox,
                "trimbox": trimbox,
                "detected_dielines": detected_dielines,
                "dieline_layers": layer_report,
                "spot_colors": spot_colors,
                "has_cutcontour": has_cutcontour
            }
            
        finally:
            if self.doc:
                self.doc.close()
                
    def _detect_dielines(self, page) -> List[Dict[str, Any]]:
        """Detect dieline paths in the page, focusing on stans dielines"""
        dielines = []
        stans_dielines = []
        cut_marks = []
        
        try:
            # Get trimbox dimensions for comparison
            trimbox = page.trimbox if page.trimbox != page.mediabox else None
            if trimbox:
                trimbox_width = (trimbox.x1 - trimbox.x0) * self.POINTS_TO_MM
                trimbox_height = (trimbox.y1 - trimbox.y0) * self.POINTS_TO_MM
                trimbox_area = {
                    'x0': trimbox.x0 * self.POINTS_TO_MM,
                    'y0': trimbox.y0 * self.POINTS_TO_MM,
                    'x1': trimbox.x1 * self.POINTS_TO_MM,
                    'y1': trimbox.y1 * self.POINTS_TO_MM
                }
            else:
                # Use mediabox if no trimbox
                mediabox = page.mediabox
                trimbox_width = (mediabox.x1 - mediabox.x0) * self.POINTS_TO_MM
                trimbox_height = (mediabox.y1 - mediabox.y0) * self.POINTS_TO_MM
                trimbox_area = {
                    'x0': mediabox.x0 * self.POINTS_TO_MM,
                    'y0': mediabox.y0 * self.POINTS_TO_MM,
                    'x1': mediabox.x1 * self.POINTS_TO_MM,
                    'y1': mediabox.y1 * self.POINTS_TO_MM
                }
            
            # Get all drawings/paths from the page
            drawings = page.get_drawings()
            
            for i, drawing in enumerate(drawings):
                # Check if this could be a dieline based on properties
                line_width = drawing.get('width', 0) or 0
                stroke_color = drawing.get('stroke')
                fill_color = drawing.get('fill')
                rect = drawing.get('rect')
                path_type = drawing.get('type', '')
                
                # Dielines are typically thin stroke-only paths
                is_stroke_only = (stroke_color is not None and fill_color is None) or path_type in ['s', 'S']
                is_thin_line = line_width <= 1.0
                
                if is_stroke_only and is_thin_line and rect:
                    # Convert bounding box to mm
                    bbox_mm = {
                        'x0': round(rect.x0 * self.POINTS_TO_MM, 2),
                        'y0': round(rect.y0 * self.POINTS_TO_MM, 2),
                        'x1': round(rect.x1 * self.POINTS_TO_MM, 2),
                        'y1': round(rect.y1 * self.POINTS_TO_MM, 2)
                    }
                    
                    # Calculate dimensions
                    path_width = bbox_mm['x1'] - bbox_mm['x0']
                    path_height = bbox_mm['y1'] - bbox_mm['y0']
                    
                    dieline_info = {
                        'index': i,
                        'line_width': round(line_width * self.POINTS_TO_MM, 2),
                        'stroke_color': stroke_color,
                        'bounding_box': bbox_mm,
                        'path_type': path_type,
                        'path_width': round(path_width, 2),
                        'path_height': round(path_height, 2),
                        'is_potential_dieline': True,
                        'dieline_type': 'unknown'
                    }
                    
                    # Classify the dieline
                    dieline_type = self._classify_dieline(
                        bbox_mm, path_width, path_height, 
                        trimbox_area, trimbox_width, trimbox_height
                    )
                    dieline_info['dieline_type'] = dieline_type
                    
                    if dieline_type == 'stans_dieline':
                        stans_dielines.append(dieline_info)
                    elif dieline_type == 'cut_mark':
                        cut_marks.append(dieline_info)
                    else:
                        dielines.append(dieline_info)
                    
        except Exception as e:
            print(f"Error detecting dielines: {e}")
        
        # Combine results with stans dielines first
        all_dielines = stans_dielines + dielines + cut_marks
        return all_dielines

    def _classify_dieline(self, bbox, path_width, path_height, trimbox_area, trimbox_width, trimbox_height):
        """Classify a dieline as stans dieline, cut mark, or other"""
        
        # Check if this is a cut registration mark (very small or at edges)
        if path_width < 1.0 or path_height < 1.0:
            return 'cut_mark'
            
        # Check if it's at the PDF edges (registration marks)
        pdf_edge_tolerance = 2.0  # mm
        if (bbox['x0'] < pdf_edge_tolerance or bbox['y0'] < pdf_edge_tolerance or 
            abs(bbox['x1'] - (trimbox_area['x1'] + 7.41)) < pdf_edge_tolerance or  # Account for typical margin
            abs(bbox['y1'] - (trimbox_area['y1'] + 7.41)) < pdf_edge_tolerance):
            return 'cut_mark'
            
        # Check if dimensions roughly match trimbox (stans dieline)
        width_match = abs(path_width - trimbox_width) < 2.0  # 2mm tolerance
        height_match = abs(path_height - trimbox_height) < 2.0
        
        if width_match and height_match:
            return 'stans_dieline'
            
        # Check if it's positioned within the trimbox area (potential stans dieline)
        center_x = (bbox['x0'] + bbox['x1']) / 2
        center_y = (bbox['y0'] + bbox['y1']) / 2
        trimbox_center_x = (trimbox_area['x0'] + trimbox_area['x1']) / 2
        trimbox_center_y = (trimbox_area['y0'] + trimbox_area['y1']) / 2
        
        # If centered in trimbox area, could be stans dieline
        if (abs(center_x - trimbox_center_x) < 5.0 and 
            abs(center_y - trimbox_center_y) < 5.0 and
            path_width > 10.0 and path_height > 10.0):  # Reasonable size
            return 'stans_dieline'
            
        return 'other_dieline'

    def _collect_layered_dielines(self, page) -> Dict[str, Any]:
        report = {
            'segments': [],
            'layer_mismatch': False,
        }

        try:
            drawings = page.get_cdrawings()
        except Exception as exc:  # pragma: no cover - diagnostic
            print(f"Unable to inspect drawings: {exc}")
            return report

        canonical_layers: Set[str] = set()
        raw_layers: Set[str] = set()

        for drawing in drawings:
            if drawing.get('type', '').lower() != 's':
                continue

            layer_name = drawing.get('layer') or 'unnamed'
            color = drawing.get('color')
            width = drawing.get('width')
            bbox = drawing.get('rect')

            segment = {
                'layer': layer_name,
                'stroke_color': self._normalize_color_components(color),
                'line_width': round(width * self.POINTS_TO_MM, 3) if width else None,
                'bounding_box': {
                    'x0': round(bbox[0] * self.POINTS_TO_MM, 2),
                    'y0': round(bbox[1] * self.POINTS_TO_MM, 2),
                    'x1': round(bbox[2] * self.POINTS_TO_MM, 2),
                    'y1': round(bbox[3] * self.POINTS_TO_MM, 2),
                } if bbox else None,
            }

            report['segments'].append(segment)
            canonical_layers.add(self._canonical_layer_name(layer_name))
            raw_layers.add(layer_name)

        # Flag if dieline-style layers are spread across multiple entries
        canon_without_other = {name for name in canonical_layers if name != 'other'}
        if len(canon_without_other) > 1:
            report['layer_mismatch'] = True

        # If we have both a named dieline layer and an unnamed/other layer, flag mismatch
        if canon_without_other and 'other' in canonical_layers:
            report['layer_mismatch'] = True

        # Fallback: multiple raw layer names for dieline strokes is also a mismatch
        if len(raw_layers) > 1:
            report['layer_mismatch'] = True

        return report

    def _canonical_layer_name(self, layer_name: str) -> str:
        cleaned = layer_name.replace(' ', '').replace('_', '').lower()
        for keyword in self.DIELINE_LAYER_KEYWORDS:
            if keyword in cleaned:
                return keyword
        return 'other'

    def _normalize_color_components(self, color: Any) -> Optional[List[float]]:
        if color is None:
            return None

        if isinstance(color, (list, tuple)):
            return [round(float(component), 4) for component in color]

        try:
            return [round(float(color), 4)]
        except (TypeError, ValueError):
            return None
        
    def _extract_spot_colors(self) -> List[str]:
        """Extract spot colors from the PDF"""
        spot_colors = []
        
        try:
            # Analyze each page with pypdf
            for page_num, page in enumerate(self.reader.pages):
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    colorspaces = page['/Resources']['/ColorSpace']
                    
                    for cs_name, cs_def in colorspaces.items():
                        # Extract color names from colorspace definitions
                        color_name = self._parse_colorspace_for_name(cs_def)
                        if color_name and color_name not in spot_colors:
                            spot_colors.append(color_name)
                            
        except Exception as e:
            print(f"Error extracting spot colors: {e}")
            
        return spot_colors
        
    def _parse_colorspace_for_name(self, cs_def) -> Optional[str]:
        """Parse colorspace definition to extract color name"""
        try:
            # Convert to string to handle IndirectObjects
            cs_def_str = str(cs_def)
            
            # Look for Separation colorspace patterns
            for target_color in self.TARGET_SPOT_COLORS:
                if f"'/{target_color}'" in cs_def_str or f'"{target_color}"' in cs_def_str:
                    return target_color
                    
            # Try direct access if possible
            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__'):
                if len(cs_def) > 1:
                    cs_type = str(cs_def[0]).replace('/', '')
                    if cs_type == 'Separation' and len(cs_def) >= 2:
                        color_name = str(cs_def[1]).replace('/', '')
                        return color_name
                        
        except Exception:
            pass
            
        return None
        
    def _is_target_color(self, color_name: str) -> bool:
        """Check if color name is a target dieline color"""
        if not color_name:
            return False
            
        color_lower = color_name.lower()
        for target in self.TARGET_SPOT_COLORS:
            if color_lower == target.lower():
                return True
                
        # Check for partial matches
        dieline_keywords = ['cutcontour', 'kisscut', 'diecut', 'stans']
        return any(keyword in color_lower for keyword in dieline_keywords)
        
    def get_trimbox_or_mediabox(self, pdf_path: str) -> Dict[str, float]:
        """Get trimbox if available, otherwise return mediabox"""
        analysis = self.analyze_pdf(pdf_path)
        return analysis.get('trimbox') or analysis.get('mediabox')
