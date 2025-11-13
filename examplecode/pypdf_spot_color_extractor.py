#!/usr/bin/env python3
"""
PyPDF Spot Color Extractor

This module uses the pypdf library (successor to PyPDF2) to extract spot color
information from PDFs by analyzing color space objects, separation colors,
and DeviceN color spaces directly from the PDF structure.
"""

import json
import re
from typing import Dict, List, Any, Set, Optional
from datetime import datetime
import os

try:
    import pypdf
except ImportError:
    print("pypdf library not found. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
    import pypdf

class PyPDFSpotColorExtractor:
    """Extract spot colors from PDFs using pypdf library."""
    
    def __init__(self):
        """Initialize the spot color extractor."""
        self.debug = True
        
    def extract_spot_colors(self, pdf_path: str) -> Dict[str, Any]:
        """Extract spot colors from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing extracted spot color information
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                
                results = {
                    'pdf_path': pdf_path,
                    'total_pages': len(reader.pages),
                    'spot_colors_found': [],
                    'separation_colors': [],
                    'devicen_colors': [],
                    'color_spaces': [],
                    'page_analysis': [],
                    'object_analysis': [],
                    'raw_content_analysis': []
                }
                
                # Analyze each page
                for page_num, page in enumerate(reader.pages, 1):
                    page_results = self._analyze_page(page, page_num)
                    if page_results:
                        results['page_analysis'].append(page_results)
                        
                        # Merge page-specific results
                        for key in ['spot_colors_found', 'separation_colors', 'devicen_colors', 'color_spaces']:
                            if key in page_results:
                                results[key].extend(page_results[key])
                
                # Analyze PDF objects directly
                object_results = self._analyze_pdf_objects(reader)
                results['object_analysis'] = object_results
                
                # Merge object analysis results
                for obj_result in object_results:
                    if 'spot_colors' in obj_result:
                        results['spot_colors_found'].extend(obj_result['spot_colors'])
                    if 'separation_colors' in obj_result:
                        results['separation_colors'].extend(obj_result['separation_colors'])
                    if 'devicen_colors' in obj_result:
                        results['devicen_colors'].extend(obj_result['devicen_colors'])
                
                # Deduplicate results
                results = self._deduplicate_results(results)
                
                # Create summary
                results['summary'] = self._create_summary(results)
                
                return results
                
        except Exception as e:
            return {
                'error': str(e),
                'pdf_path': pdf_path,
                'total_pages': 0,
                'spot_colors_found': [],
                'summary': {'error': str(e)}
            }
    
    def _analyze_page(self, page: pypdf.PageObject, page_num: int) -> Dict[str, Any]:
        """Analyze a single page for spot colors.
        
        Args:
            page: pypdf PageObject
            page_num: Page number (1-indexed)
            
        Returns:
            Dictionary with page analysis results
        """
        page_results = {
            'page': page_num,
            'spot_colors_found': [],
            'separation_colors': [],
            'devicen_colors': [],
            'color_spaces': [],
            'content_streams': []
        }
        
        try:
            # Get page resources
            if '/Resources' in page:
                resources = page['/Resources']
                if self.debug:
                    print(f"Page {page_num} resources: {type(resources)}")
                
                # Analyze ColorSpace resources
                if '/ColorSpace' in resources:
                    colorspaces = resources['/ColorSpace']
                    cs_results = self._analyze_colorspaces(colorspaces, page_num)
                    page_results['color_spaces'].extend(cs_results)
                    
                    # Extract spot colors from colorspaces
                    for cs in cs_results:
                        if cs.get('type') == 'Separation':
                            page_results['separation_colors'].append(cs)
                            if cs.get('color_name'):
                                page_results['spot_colors_found'].append({
                                    'name': cs['color_name'],
                                    'type': 'Separation',
                                    'page': page_num,
                                    'source': 'ColorSpace'
                                })
                        elif cs.get('type') == 'DeviceN':
                            page_results['devicen_colors'].append(cs)
                            if cs.get('color_names'):
                                for color_name in cs['color_names']:
                                    page_results['spot_colors_found'].append({
                                        'name': color_name,
                                        'type': 'DeviceN',
                                        'page': page_num,
                                        'source': 'ColorSpace'
                                    })
            
            # Analyze page content streams
            try:
                content = page.extract_text()  # This might help us find text-based references
                if content:
                    content_analysis = self._analyze_content_stream(content, page_num)
                    if content_analysis:
                        page_results['content_streams'].append(content_analysis)
            except Exception as e:
                if self.debug:
                    print(f"Could not extract text from page {page_num}: {e}")
            
            # Try to get raw content stream
            try:
                if '/Contents' in page:
                    contents = page['/Contents']
                    if hasattr(contents, 'get_data'):
                        raw_content = contents.get_data().decode('latin-1', errors='ignore')
                        raw_analysis = self._analyze_raw_content(raw_content, page_num)
                        if raw_analysis:
                            page_results['content_streams'].append(raw_analysis)
            except Exception as e:
                if self.debug:
                    print(f"Could not get raw content from page {page_num}: {e}")
            
        except Exception as e:
            if self.debug:
                print(f"Error analyzing page {page_num}: {e}")
        
        return page_results if any(page_results[key] for key in ['spot_colors_found', 'separation_colors', 'devicen_colors', 'color_spaces', 'content_streams']) else None
    
    def _analyze_colorspaces(self, colorspaces: Any, page_num: int) -> List[Dict[str, Any]]:
        """Analyze ColorSpace dictionary for spot colors.
        
        Args:
            colorspaces: ColorSpace dictionary from PDF
            page_num: Page number
            
        Returns:
            List of colorspace analysis results
        """
        results = []
        
        try:
            if hasattr(colorspaces, 'items'):
                for cs_name, cs_def in colorspaces.items():
                    if self.debug:
                        print(f"Analyzing colorspace: {cs_name} = {cs_def}")
                    
                    cs_result = {
                        'name': cs_name,
                        'page': page_num,
                        'definition': str(cs_def),
                        'type': 'Unknown'
                    }
                    
                    # Check if it's a list/array (typical for color space definitions)
                    if hasattr(cs_def, '__iter__') and not isinstance(cs_def, str):
                        cs_list = list(cs_def) if hasattr(cs_def, '__iter__') else [cs_def]
                        
                        if len(cs_list) > 0:
                            cs_type = str(cs_list[0]).replace('/', '')
                            cs_result['type'] = cs_type
                            
                            if cs_type == 'Separation' and len(cs_list) >= 2:
                                # Separation colorspace: [/Separation /ColorName /AlternateSpace /TintTransform]
                                color_name = str(cs_list[1]).replace('/', '')
                                cs_result['color_name'] = color_name
                                cs_result['alternate_space'] = str(cs_list[2]) if len(cs_list) > 2 else None
                                
                                if self.debug:
                                    print(f"Found Separation color: {color_name}")
                            
                            elif cs_type == 'DeviceN' and len(cs_list) >= 2:
                                # DeviceN colorspace: [/DeviceN [/Color1 /Color2 ...] /AlternateSpace /TintTransform]
                                if hasattr(cs_list[1], '__iter__'):
                                    color_names = [str(name).replace('/', '') for name in cs_list[1]]
                                    cs_result['color_names'] = color_names
                                    cs_result['alternate_space'] = str(cs_list[2]) if len(cs_list) > 2 else None
                                    
                                    if self.debug:
                                        print(f"Found DeviceN colors: {color_names}")
                    
                    results.append(cs_result)
            
        except Exception as e:
            if self.debug:
                print(f"Error analyzing colorspaces: {e}")
        
        return results
    
    def _analyze_content_stream(self, content: str, page_num: int) -> Optional[Dict[str, Any]]:
        """Analyze content stream for color operations.
        
        Args:
            content: Content stream text
            page_num: Page number
            
        Returns:
            Content analysis results or None
        """
        try:
            # Look for potential spot color names in text
            spot_color_patterns = [
                r'\b([A-Za-z0-9_]*[Cc]ut[A-Za-z0-9_]*)\b',
                r'\b([A-Za-z0-9_]*[Dd]ie[A-Za-z0-9_]*)\b',
                r'\b([A-Za-z0-9_]*[Cc]ontour[A-Za-z0-9_]*)\b',
                r'\b(PANTONE[^\s]+)\b',
                r'\b(PMS[^\s]+)\b'
            ]
            
            found_colors = []
            for pattern in spot_color_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if match and match not in found_colors:
                        found_colors.append(match)
            
            if found_colors:
                return {
                    'type': 'text_content',
                    'page': page_num,
                    'potential_spot_colors': found_colors,
                    'content_length': len(content)
                }
        
        except Exception as e:
            if self.debug:
                print(f"Error analyzing content stream: {e}")
        
        return None
    
    def _analyze_raw_content(self, raw_content: str, page_num: int) -> Optional[Dict[str, Any]]:
        """Analyze raw PDF content stream.
        
        Args:
            raw_content: Raw content stream
            page_num: Page number
            
        Returns:
            Raw content analysis results or None
        """
        try:
            # Look for color space operations
            color_ops = []
            
            # Color space setting operations
            cs_patterns = [
                (r'/([A-Za-z0-9_]+)\s+cs', 'stroke_colorspace'),
                (r'/([A-Za-z0-9_]+)\s+CS', 'fill_colorspace'),
                (r'/([A-Za-z0-9_]+)\s+sc', 'stroke_color'),
                (r'/([A-Za-z0-9_]+)\s+SC', 'fill_color')
            ]
            
            for pattern, op_type in cs_patterns:
                matches = re.finditer(pattern, raw_content)
                for match in matches:
                    color_name = match.group(1)
                    color_ops.append({
                        'operation': op_type,
                        'color_name': color_name,
                        'position': match.start()
                    })
            
            # Look for potential spot color names
            spot_patterns = [
                r'/([A-Za-z0-9_]*[Cc]ut[A-Za-z0-9_]*)',
                r'/([A-Za-z0-9_]*[Dd]ie[A-Za-z0-9_]*)',
                r'/([A-Za-z0-9_]*[Cc]ontour[A-Za-z0-9_]*)',
                r'/(PANTONE[^\s\[\]<>()]+)',
                r'/(PMS[^\s\[\]<>()]+)'
            ]
            
            potential_spots = []
            for pattern in spot_patterns:
                matches = re.findall(pattern, raw_content, re.IGNORECASE)
                for match in matches:
                    if match and match not in potential_spots:
                        potential_spots.append(match)
            
            if color_ops or potential_spots:
                return {
                    'type': 'raw_content',
                    'page': page_num,
                    'color_operations': color_ops,
                    'potential_spot_colors': potential_spots,
                    'content_length': len(raw_content)
                }
        
        except Exception as e:
            if self.debug:
                print(f"Error analyzing raw content: {e}")
        
        return None
    
    def _analyze_pdf_objects(self, reader: pypdf.PdfReader) -> List[Dict[str, Any]]:
        """Analyze PDF objects directly for color information.
        
        Args:
            reader: pypdf PdfReader instance
            
        Returns:
            List of object analysis results
        """
        results = []
        
        try:
            # Try to access the PDF's object structure
            if hasattr(reader, 'trailer') and reader.trailer:
                # Analyze the trailer and root objects
                root_analysis = self._analyze_object_tree(reader.trailer, 'trailer')
                if root_analysis:
                    results.append(root_analysis)
        
        except Exception as e:
            if self.debug:
                print(f"Error analyzing PDF objects: {e}")
        
        return results
    
    def _analyze_object_tree(self, obj: Any, obj_type: str) -> Optional[Dict[str, Any]]:
        """Recursively analyze PDF object tree for color information.
        
        Args:
            obj: PDF object to analyze
            obj_type: Type description of the object
            
        Returns:
            Object analysis results or None
        """
        try:
            obj_str = str(obj)
            
            # Look for color-related keywords
            color_keywords = ['ColorSpace', 'Separation', 'DeviceN', 'Pattern']
            spot_keywords = ['Cut', 'Die', 'Contour', 'PANTONE', 'PMS']
            
            found_colors = []
            found_spots = []
            
            for keyword in color_keywords:
                if keyword.lower() in obj_str.lower():
                    found_colors.append(keyword)
            
            for keyword in spot_keywords:
                if keyword.lower() in obj_str.lower():
                    # Try to extract the actual color name
                    pattern = rf'\b({keyword}[A-Za-z0-9_]*)\b'
                    matches = re.findall(pattern, obj_str, re.IGNORECASE)
                    found_spots.extend(matches)
            
            if found_colors or found_spots:
                return {
                    'object_type': obj_type,
                    'color_keywords': found_colors,
                    'spot_colors': found_spots,
                    'object_preview': obj_str[:200] + '...' if len(obj_str) > 200 else obj_str
                }
        
        except Exception as e:
            if self.debug:
                print(f"Error analyzing object tree: {e}")
        
        return None
    
    def _deduplicate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Remove duplicate entries from results.
        
        Args:
            results: Results dictionary
            
        Returns:
            Deduplicated results
        """
        # Deduplicate spot colors
        seen_spots = set()
        unique_spots = []
        
        for spot in results['spot_colors_found']:
            spot_key = (spot.get('name', ''), spot.get('type', ''), spot.get('page', 0))
            if spot_key not in seen_spots:
                seen_spots.add(spot_key)
                unique_spots.append(spot)
        
        results['spot_colors_found'] = unique_spots
        
        return results
    
    def _create_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of extraction results.
        
        Args:
            results: Full results dictionary
            
        Returns:
            Summary dictionary
        """
        summary = {
            'total_spot_colors': len(results['spot_colors_found']),
            'unique_color_names': list(set(spot['name'] for spot in results['spot_colors_found'] if spot.get('name'))),
            'separation_colors_count': len(results['separation_colors']),
            'devicen_colors_count': len(results['devicen_colors']),
            'pages_analyzed': len(results['page_analysis']),
            'objects_analyzed': len(results['object_analysis'])
        }
        
        # Categorize potential dieline colors
        dieline_keywords = ['cut', 'die', 'contour', 'kiss', 'perf', 'crease', 'fold', 'knife']
        summary['potential_dieline_colors'] = [
            color for color in summary['unique_color_names']
            if any(keyword in color.lower() for keyword in dieline_keywords)
        ]
        
        return summary

def analyze_pdf_spot_colors(pdf_path: str, save_results: bool = True) -> Dict[str, Any]:
    """Analyze PDF for spot colors and save results.
    
    Args:
        pdf_path: Path to PDF file
        save_results: Whether to save results to JSON file
        
    Returns:
        Analysis results
    """
    extractor = PyPDFSpotColorExtractor()
    results = extractor.extract_spot_colors(pdf_path)
    
    # Print summary
    print(f"\n🎨 PyPDF Spot Color Analysis: {pdf_path}")
    print(f"   Total pages: {results.get('total_pages', 0)}")
    
    if 'summary' in results and 'error' not in results['summary']:
        summary = results['summary']
        print(f"   Total spot colors found: {summary['total_spot_colors']}")
        print(f"   Separation colors: {summary['separation_colors_count']}")
        print(f"   DeviceN colors: {summary['devicen_colors_count']}")
        print(f"   Pages analyzed: {summary['pages_analyzed']}")
        print(f"   Objects analyzed: {summary['objects_analyzed']}")
        
        if summary['unique_color_names']:
            print(f"\n🎨 Unique Color Names Found:")
            for color in summary['unique_color_names']:
                print(f"   - {color}")
        
        if summary['potential_dieline_colors']:
            print(f"\n🔍 Potential Dieline Colors:")
            for color in summary['potential_dieline_colors']:
                print(f"   - {color}")
        
        if not summary['unique_color_names']:
            print(f"\n❌ No spot colors found")
    
    elif 'error' in results:
        print(f"\n❌ Error: {results['error']}")
    
    # Save results if requested
    if save_results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pypdf_spot_colors_{os.path.basename(pdf_path).replace('.PDF', '')}_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    # Test with the specific PDF mentioned by the user
    test_pdf = "ai_data/test-pdfs/5122482_7914597/5122482_7914597.PDF"
    analyze_pdf_spot_colors(test_pdf, save_results=True)