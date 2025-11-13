#!/usr/bin/env python3
"""
CutContour and KissCut Extractor

Specifically designed for shape recognition detection by targeting:
- CutContour spot colors
- KissCut spot colors
- Related cutting/kissing spot color variations

This extractor focuses on the actual cutting paths used in shape recognition,
not generic dielines or die cuts.
"""

import argparse
import json
import os
import sys
from typing import List, Dict, Tuple, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF not found. Installing...")
    os.system("pip install PyMuPDF")
    import fitz

try:
    from pypdf import PdfReader
except ImportError:
    print("pypdf not found. Installing...")
    os.system("pip install pypdf")
    from pypdf import PdfReader

class CutContourExtractor:
    """Extract CutContour and KissCut elements for shape recognition."""
    
    # Target spot colors for shape recognition
    TARGET_SPOT_COLORS = [
        'CutContour',
        'KissCut', 
        'Kiss Cut',
        'Cut Contour',
        'cutcontour',
        'kisscut',
        'kiss cut',
        'cut contour',
        'CUTCONTOUR',
        'KISSCUT',
        'CUT CONTOUR',
        'KISS CUT'
    ]
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
    def extract_cutcontour_paths(self, pdf_path: str) -> Dict:
        """Extract CutContour and KissCut paths from PDF."""
        if self.debug:
            print(f"🔍 Analyzing PDF for CutContour/KissCut: {pdf_path}")
        
        results = {
            'input_path': pdf_path,
            'target_colors': self.TARGET_SPOT_COLORS,
            'total_pages': 0,
            'cutcontour_pages': 0,
            'extraction_methods': {
                'spot_color_analysis': True,
                'geometric_analysis': True,
                'cross_reference_matching': True
            },
            'page_results': []
        }
        
        # Open PDF with both libraries
        doc = fitz.open(pdf_path)
        reader = PdfReader(pdf_path)
        
        results['total_pages'] = len(doc)
        
        for page_num in range(len(doc)):
            if self.debug:
                print(f"\n📄 Processing page {page_num + 1}...")
            
            page_result = self._analyze_page_for_cutcontour(
                doc[page_num], reader.pages[page_num], page_num + 1
            )
            
            results['page_results'].append(page_result)
            
            if page_result['has_cutcontour']:
                results['cutcontour_pages'] += 1
        
        doc.close()
        
        if self.debug:
            print(f"\n✅ Analysis complete: {results['cutcontour_pages']}/{results['total_pages']} pages with CutContour/KissCut")
        
        return results
    
    def _analyze_page_for_cutcontour(self, fitz_page, pypdf_page, page_num: int) -> Dict:
        """Analyze a single page for CutContour/KissCut elements."""
        page_result = {
            'page': page_num,
            'has_cutcontour': False,
            'spot_color_analysis': {},
            'geometric_analysis': {},
            'matched_elements': [],
            'summary': {}
        }
        
        # Step 1: Analyze spot colors using pypdf
        spot_analysis = self._analyze_spot_colors(pypdf_page)
        page_result['spot_color_analysis'] = spot_analysis
        
        # Step 2: Analyze geometric elements using PyMuPDF
        geometric_analysis = self._analyze_geometric_elements(fitz_page)
        page_result['geometric_analysis'] = geometric_analysis
        
        # Step 3: Cross-reference and match elements
        matched_elements = self._match_spot_colors_to_geometry(
            spot_analysis, geometric_analysis, fitz_page
        )
        page_result['matched_elements'] = matched_elements
        
        # Step 4: Determine if page has relevant CutContour/KissCut
        page_result['has_cutcontour'] = len(matched_elements) > 0 or len(spot_analysis['found_target_colors']) > 0
        
        # Step 5: Generate summary
        page_result['summary'] = self._generate_page_summary(page_result)
        
        if self.debug and page_result['has_cutcontour']:
            print(f"  ✅ Found {len(spot_analysis['found_target_colors'])} target colors, {len(matched_elements)} matched elements")
        
        return page_result
    
    def _analyze_spot_colors(self, pypdf_page) -> Dict:
        """Analyze spot colors in the page using pypdf."""
        analysis = {
            'found_target_colors': [],
            'all_colorspaces': [],
            'separation_colors': [],
            'devicen_colors': []
        }
        
        try:
            # Get page resources
            if '/Resources' in pypdf_page:
                resources = pypdf_page['/Resources']
                
                # Analyze ColorSpace resources
                if '/ColorSpace' in resources:
                    colorspaces = resources['/ColorSpace']
                    
                    for cs_name, cs_def in colorspaces.items():
                        colorspace_info = self._parse_colorspace_definition(cs_name, cs_def)
                        analysis['all_colorspaces'].append(colorspace_info)
                        
                        # Check if this is a target color
                        if colorspace_info['type'] == 'Separation':
                            analysis['separation_colors'].append(colorspace_info)
                            color_name = colorspace_info.get('color_name', '')
                            
                            if self._is_target_color(color_name):
                                analysis['found_target_colors'].append(colorspace_info)
                                if self.debug:
                                    print(f"    🎯 Found target color: {color_name}")
                        
                        elif colorspace_info['type'] == 'DeviceN':
                            analysis['devicen_colors'].append(colorspace_info)
                            color_names = colorspace_info.get('color_names', [])
                            
                            for color_name in color_names:
                                if self._is_target_color(color_name):
                                    analysis['found_target_colors'].append({
                                        **colorspace_info,
                                        'matched_color': color_name
                                    })
                                    if self.debug:
                                        print(f"    🎯 Found target color in DeviceN: {color_name}")
        
        except Exception as e:
            if self.debug:
                print(f"    ⚠️ Error analyzing spot colors: {e}")
        
        return analysis
    
    def _parse_colorspace_definition(self, cs_name: str, cs_def) -> Dict:
        """Parse colorspace definition to extract color information."""
        colorspace_info = {
            'name': cs_name,
            'definition': str(cs_def),
            'type': 'Unknown',
            'color_name': None,
            'color_names': []
        }
        
        try:
            # First, try to extract color name from the string representation
            # This handles cases where IndirectObjects prevent direct access
            definition_str = str(cs_def)
            
            # Look for Separation colorspace pattern in string
            if "'/Separation'" in definition_str and "'/CutContour'" in definition_str:
                colorspace_info['type'] = 'Separation'
                colorspace_info['color_name'] = 'CutContour'
                if self.debug:
                    print(f"    🎯 Found CutContour in definition string: {cs_name}")
                return colorspace_info
            
            # Look for other target colors in definition string
            for target_color in self.TARGET_SPOT_COLORS:
                if f"'/{target_color}'" in definition_str or f'"{target_color}"' in definition_str:
                    colorspace_info['type'] = 'Separation'
                    colorspace_info['color_name'] = target_color
                    if self.debug:
                        print(f"    🎯 Found {target_color} in definition string: {cs_name}")
                    return colorspace_info
            
            # Try direct access if string parsing didn't work
            # Check if cs_def is accessible before trying to get length
            if not hasattr(cs_def, '__getitem__'):
                return colorspace_info
            
            # Handle IndirectObject references
            try:
                cs_def_length = len(cs_def)
            except (TypeError, AttributeError):
                # Can't get length, try to access first element directly
                try:
                    first_element = cs_def[0]
                    cs_def_length = 1  # At least one element
                except (TypeError, IndexError, KeyError):
                    return colorspace_info
            
            if cs_def_length > 0:
                try:
                    cs_type = str(cs_def[0]).replace('/', '')
                    colorspace_info['type'] = cs_type
                    
                    if cs_type == 'Separation' and cs_def_length >= 2:
                        # Separation colorspace: [/Separation /ColorName /AlternateSpace /TintTransform]
                        try:
                            color_name = str(cs_def[1]).replace('/', '')
                            colorspace_info['color_name'] = color_name
                        except (TypeError, IndexError, KeyError):
                            pass
                    
                    elif cs_type == 'DeviceN' and cs_def_length >= 2:
                        # DeviceN colorspace: [/DeviceN [/Color1 /Color2 ...] /AlternateSpace /TintTransform]
                        try:
                            color_list = cs_def[1]
                            if hasattr(color_list, '__iter__'):
                                color_names = [str(name).replace('/', '') for name in color_list]
                                colorspace_info['color_names'] = color_names
                        except (TypeError, IndexError, KeyError):
                            pass
                except (TypeError, IndexError, KeyError):
                    pass
        
        except Exception as e:
            if self.debug:
                print(f"    ⚠️ Error parsing colorspace {cs_name}: {e}")
        
        return colorspace_info
    
    def _is_target_color(self, color_name: str) -> bool:
        """Check if color name matches target CutContour/KissCut colors."""
        if not color_name:
            return False
        
        color_name_clean = color_name.strip()
        
        # Exact matches
        if color_name_clean in self.TARGET_SPOT_COLORS:
            return True
        
        # Case-insensitive matches
        color_lower = color_name_clean.lower()
        for target in self.TARGET_SPOT_COLORS:
            if color_lower == target.lower():
                return True
        
        # Partial matches for variations
        cutcontour_variations = ['cutcontour', 'cut contour', 'cut_contour']
        kisscut_variations = ['kisscut', 'kiss cut', 'kiss_cut']
        
        for variation in cutcontour_variations + kisscut_variations:
            if variation in color_lower or color_lower in variation:
                return True
        
        return False
    
    def _analyze_geometric_elements(self, fitz_page) -> Dict:
        """Analyze geometric elements using PyMuPDF."""
        analysis = {
            'total_paths': 0,
            'thin_paths': [],
            'stroke_only_paths': [],
            'potential_cutcontour_paths': []
        }
        
        try:
            # Get drawing commands
            drawings = fitz_page.get_drawings()
            analysis['total_paths'] = len(drawings)
            
            for i, drawing in enumerate(drawings):
                path_info = {
                    'path_index': i,
                    'line_width': drawing.get('width', 0),
                    'stroke_color': drawing.get('stroke', None),
                    'fill_color': drawing.get('fill', None),
                    'bounding_box': str(drawing.get('rect', '')),
                    'path_type': drawing.get('type', ''),
                    'items': drawing.get('items', []),
                    'is_thin_line': False,
                    'is_stroke_only': False,
                    'is_potential_cutcontour': False
                }
                
                # Analyze path characteristics
                line_width = path_info['line_width']
                has_stroke = path_info['stroke_color'] is not None
                has_fill = path_info['fill_color'] is not None
                
                # Analyze path properties
                is_thin_line = line_width <= 1.0
                # Check for stroke-only operations more comprehensively
                is_stroke_only = (
                    path_info['path_type'] in ['s', 'S'] or  # explicit stroke operations
                    (has_stroke and not has_fill) or  # has stroke but no fill
                    (line_width > 0 and not has_fill)  # has line width but no fill
                )
                # More inclusive criteria for potential cutcontour
                is_potential_cutcontour = (
                    is_thin_line or  # any thin line could be cutcontour
                    line_width <= 0.5 or  # very thin lines are likely cutcontour
                    (is_stroke_only and line_width <= 2.0)  # stroke-only paths with reasonable width
                )
                
                # Check for thin lines (typical for cutting paths)
                if is_thin_line:  # Thin lines
                    path_info['is_thin_line'] = True
                    analysis['thin_paths'].append(path_info)
                
                # Check for stroke-only paths (no fill)
                if is_stroke_only:
                    path_info['is_stroke_only'] = True
                    analysis['stroke_only_paths'].append(path_info)
                
                # Check if this path could be a cutcontour based on various criteria
                if is_potential_cutcontour:
                    path_info['is_potential_cutcontour'] = True
                    analysis['potential_cutcontour_paths'].append(path_info)
        
        except Exception as e:
            if self.debug:
                print(f"    ⚠️ Error analyzing geometric elements: {e}")
        
        return analysis
    
    def _match_spot_colors_to_geometry(self, spot_analysis: Dict, geometric_analysis: Dict, fitz_page) -> List[Dict]:
        """Match spot color definitions to geometric elements."""
        matched_elements = []
        
        # If we found target spot colors, try to identify which geometric elements use them
        if spot_analysis['found_target_colors']:
            
            # For now, prioritize potential CutContour paths when target colors are found
            for path in geometric_analysis['potential_cutcontour_paths']:
                for target_color in spot_analysis['found_target_colors']:
                    # Enhanced matching for CutContour elements
                    match_reasons = ['Thin stroke-only path with target spot color present']
                    confidence = 'high'
                    
                    # Check if this is specifically a CutContour color
                    color_name = target_color.get('color_name', '')
                    if 'CutContour' in color_name:
                        # Additional validation for CutContour paths
                        line_width = path.get('line_width', 0)
                        if line_width <= 0.5:
                            match_reasons.append(f'Very thin line ({line_width}pt) typical for cut contours')
                        
                        # Check if it forms geometric shapes
                        bounding_box = path.get('bounding_box', '')
                        if 'Rect' in bounding_box:
                            try:
                                coords = bounding_box.replace('Rect(', '').replace(')', '').split(', ')
                                if len(coords) >= 4:
                                    x1, y1, x2, y2 = map(float, coords[:4])
                                    width = abs(x2 - x1)
                                    height = abs(y2 - y1)
                                    
                                    if width > 5 and height > 5:
                                        match_reasons.append(f'Geometric shape ({width:.1f}x{height:.1f}) suitable for cutting')
                                        confidence = 'very_high'
                            except (ValueError, IndexError):
                                pass
                    
                    matched_element = {
                        'path_info': path,
                        'spot_color_info': target_color,
                        'match_confidence': confidence,
                        'match_reason': '; '.join(match_reasons)
                    }
                    matched_elements.append(matched_element)
            
            # If no potential CutContour paths, check thin paths
            if not matched_elements:
                for path in geometric_analysis['thin_paths']:
                    if path['is_stroke_only']:
                        for target_color in spot_analysis['found_target_colors']:
                            matched_element = {
                                'path_info': path,
                                'spot_color_info': target_color,
                                'match_confidence': 'medium',
                                'match_reason': 'Thin stroke-only path with target spot color present'
                            }
                            matched_elements.append(matched_element)
        
        return matched_elements
    
    def _generate_page_summary(self, page_result: Dict) -> Dict:
        """Generate summary of page analysis."""
        spot_analysis = page_result['spot_color_analysis']
        geometric_analysis = page_result['geometric_analysis']
        matched_elements = page_result['matched_elements']
        
        summary = {
            'target_colors_found': len(spot_analysis['found_target_colors']),
            'target_color_names': [color.get('color_name') or color.get('matched_color', 'Unknown') 
                                 for color in spot_analysis['found_target_colors']],
            'total_colorspaces': len(spot_analysis['all_colorspaces']),
            'total_paths': geometric_analysis['total_paths'],
            'potential_cutcontour_paths': len(geometric_analysis['potential_cutcontour_paths']),
            'matched_elements': len(matched_elements),
            'confidence': 'none'
        }
        
        # Determine confidence level
        if summary['matched_elements'] > 0:
            summary['confidence'] = 'high'
        elif summary['target_colors_found'] > 0:
            summary['confidence'] = 'medium'
        elif summary['potential_cutcontour_paths'] > 0:
            summary['confidence'] = 'low'
        
        return summary
    
    def save_results(self, results: Dict, output_path: str):
        """Save extraction results to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        if self.debug:
            print(f"💾 Results saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Extract CutContour and KissCut elements for shape recognition')
    parser.add_argument('pdf_path', help='Path to PDF file')
    parser.add_argument('-o', '--output', default='cutcontour_extraction_results.json',
                       help='Output JSON file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Check input file
    if not os.path.exists(args.pdf_path):
        print(f"❌ Error: PDF file '{args.pdf_path}' not found")
        sys.exit(1)
    
    # Create extractor
    extractor = CutContourExtractor(debug=args.debug)
    
    # Extract CutContour/KissCut elements
    results = extractor.extract_cutcontour_paths(args.pdf_path)
    
    # Save results
    extractor.save_results(results, args.output)
    
    # Print summary
    print(f"\n📊 CutContour/KissCut Extraction Summary:")
    print(f"   Input: {args.pdf_path}")
    print(f"   Pages analyzed: {results['total_pages']}")
    print(f"   Pages with CutContour/KissCut: {results['cutcontour_pages']}")
    
    for page_result in results['page_results']:
        if page_result['has_cutcontour']:
            summary = page_result['summary']
            print(f"   Page {page_result['page']}: {summary['target_colors_found']} target colors, "
                  f"{summary['matched_elements']} matched elements, confidence: {summary['confidence']}")
    
    print(f"   Results saved to: {args.output}")

if __name__ == '__main__':
    main()