#!/usr/bin/env python3
"""
CutContour Visualizer

Visualizes CutContour and KissCut elements extracted from PDFs for shape recognition.
Creates visual outputs to help identify cutting paths and shapes.

Usage:
    python3 cutcontour_visualizer.py <results_json> [options]

Options:
    --svg           Generate SVG visualization
    --pdf           Generate PDF with cutcontour overlay
    --shapes        Generate shape-only PDF
    --report        Generate detailed text report
    --all           Generate all output types
    --output-dir    Output directory (default: cutcontour_output)
    --debug         Enable debug output
"""

import json
import argparse
import os
from pathlib import Path
from typing import Dict, List, Any
import fitz  # PyMuPDF

class CutContourVisualizer:
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def visualize_cutcontour(self, results_path: str, output_dir: str = "cutcontour_output", 
                           generate_svg: bool = False, generate_pdf: bool = False,
                           generate_shapes: bool = False, generate_report: bool = False) -> Dict[str, Any]:
        """Visualize CutContour extraction results."""
        
        if self.debug:
            print(f"🎨 Visualizing CutContour results from: {results_path}")
        
        # Load results
        with open(results_path, 'r') as f:
            results = json.load(f)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Get input PDF path
        input_pdf_path = results['input_path']
        pdf_name = Path(input_pdf_path).stem
        
        visualization_results = {
            'input_pdf': input_pdf_path,
            'output_directory': output_dir,
            'generated_files': [],
            'summary': {
                'total_pages': results['total_pages'],
                'cutcontour_pages': results['cutcontour_pages'],
                'total_matched_elements': 0
            }
        }
        
        # Process each page with CutContour elements
        for page_result in results['page_results']:
            if not page_result['has_cutcontour']:
                continue
                
            page_num = page_result['page']
            matched_elements = page_result['matched_elements']
            
            visualization_results['summary']['total_matched_elements'] += len(matched_elements)
            
            if self.debug:
                print(f"📄 Processing page {page_num} with {len(matched_elements)} CutContour elements")
            
            # Generate SVG visualization
            if generate_svg:
                svg_path = self._generate_svg(page_result, output_dir, pdf_name, page_num)
                if svg_path:
                    visualization_results['generated_files'].append(svg_path)
            
            # Generate PDF overlay
            if generate_pdf:
                pdf_path = self._generate_pdf_overlay(input_pdf_path, page_result, output_dir, pdf_name, page_num)
                if pdf_path:
                    visualization_results['generated_files'].append(pdf_path)
            
            # Generate shapes-only PDF
            if generate_shapes:
                shapes_path = self._generate_shapes_pdf(page_result, output_dir, pdf_name, page_num)
                if shapes_path:
                    visualization_results['generated_files'].append(shapes_path)
        
        # Generate text report
        if generate_report:
            report_path = self._generate_report(results, output_dir, pdf_name)
            if report_path:
                visualization_results['generated_files'].append(report_path)
        
        if self.debug:
            print(f"✅ Visualization complete. Generated {len(visualization_results['generated_files'])} files.")
        
        return visualization_results
    
    def _generate_svg(self, page_result: Dict, output_dir: str, pdf_name: str, page_num: int) -> str:
        """Generate SVG visualization of CutContour elements."""
        try:
            matched_elements = page_result['matched_elements']
            
            # Calculate bounding box for all elements
            min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
            
            for element in matched_elements:
                path_info = element['path_info']
                bbox_str = path_info['bounding_box']
                
                # Parse bounding box
                coords = bbox_str.replace('Rect(', '').replace(')', '').split(', ')
                if len(coords) >= 4:
                    x1, y1, x2, y2 = map(float, coords[:4])
                    min_x = min(min_x, x1, x2)
                    min_y = min(min_y, y1, y2)
                    max_x = max(max_x, x1, x2)
                    max_y = max(max_y, y1, y2)
            
            # Add padding
            padding = 20
            width = max_x - min_x + 2 * padding
            height = max_y - min_y + 2 * padding
            
            # Generate SVG content
            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" viewBox="{min_x - padding} {min_y - padding} {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <title>CutContour Elements - Page {page_num}</title>
  
  <!-- Background -->
  <rect x="{min_x - padding}" y="{min_y - padding}" width="{width}" height="{height}" fill="white" stroke="#ddd" stroke-width="1"/>
  
  <!-- CutContour Elements -->
'''
            
            # Add each CutContour element
            for i, element in enumerate(matched_elements):
                path_info = element['path_info']
                confidence = element['match_confidence']
                line_width = path_info['line_width']
                
                # Color based on confidence
                color = {
                    'very_high': '#ff0000',  # Red
                    'high': '#ff4500',       # Orange Red
                    'medium': '#ffa500',     # Orange
                    'low': '#ffff00'         # Yellow
                }.get(confidence, '#ff0000')
                
                # Draw path items
                for item in path_info['items']:
                    if item[0] == 'l':  # Line
                        x1, y1 = item[1].replace('Point(', '').replace(')', '').split(', ')
                        x2, y2 = item[2].replace('Point(', '').replace(')', '').split(', ')
                        svg_content += f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{max(line_width * 2, 1)}" opacity="0.8"/>\n'
                    
                    elif item[0] == 'c':  # Curve
                        # For curves, we'll approximate with a path
                        points = [item[j].replace('Point(', '').replace(')', '') for j in range(1, len(item))]
                        if len(points) >= 3:
                            start = points[0].split(', ')
                            svg_content += f'  <path d="M {start[0]} {start[1]}'
                            for point in points[1:]:
                                coords = point.split(', ')
                                svg_content += f' L {coords[0]} {coords[1]}'
                            svg_content += f'" stroke="{color}" stroke-width="{max(line_width * 2, 1)}" fill="none" opacity="0.8"/>\n'
            
            svg_content += '</svg>'
            
            # Save SVG file
            svg_filename = f"{pdf_name}_cutcontour_page_{page_num}.svg"
            svg_path = os.path.join(output_dir, svg_filename)
            
            with open(svg_path, 'w') as f:
                f.write(svg_content)
            
            if self.debug:
                print(f"  📊 Generated SVG: {svg_filename}")
            
            return svg_path
            
        except Exception as e:
            if self.debug:
                print(f"  ⚠️ Error generating SVG: {e}")
            return None
    
    def _generate_pdf_overlay(self, input_pdf_path: str, page_result: Dict, output_dir: str, pdf_name: str, page_num: int) -> str:
        """Generate PDF with CutContour overlay."""
        try:
            # Open original PDF
            doc = fitz.open(input_pdf_path)
            page = doc[page_num - 1]  # 0-indexed
            
            matched_elements = page_result['matched_elements']
            
            # Add CutContour overlays
            for element in matched_elements:
                path_info = element['path_info']
                confidence = element['match_confidence']
                line_width = path_info['line_width']
                
                # Color based on confidence
                color = {
                    'very_high': (1, 0, 0),      # Red
                    'high': (1, 0.27, 0),        # Orange Red
                    'medium': (1, 0.65, 0),      # Orange
                    'low': (1, 1, 0)             # Yellow
                }.get(confidence, (1, 0, 0))
                
                # Draw path items
                for item in path_info['items']:
                    if item[0] == 'l':  # Line
                        x1, y1 = map(float, item[1].replace('Point(', '').replace(')', '').split(', '))
                        x2, y2 = map(float, item[2].replace('Point(', '').replace(')', '').split(', '))
                        
                        # Draw line
                        page.draw_line(fitz.Point(x1, y1), fitz.Point(x2, y2), 
                                     color=color, width=max(line_width * 3, 2))
            
            # Save overlay PDF
            overlay_filename = f"{pdf_name}_cutcontour_overlay_page_{page_num}.pdf"
            overlay_path = os.path.join(output_dir, overlay_filename)
            
            # Create new document with just this page
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_num-1, to_page=page_num-1)
            new_doc.save(overlay_path)
            new_doc.close()
            
            doc.close()
            
            if self.debug:
                print(f"  📄 Generated PDF overlay: {overlay_filename}")
            
            return overlay_path
            
        except Exception as e:
            if self.debug:
                print(f"  ⚠️ Error generating PDF overlay: {e}")
            return None
    
    def _generate_shapes_pdf(self, page_result: Dict, output_dir: str, pdf_name: str, page_num: int) -> str:
        """Generate PDF with only CutContour shapes."""
        try:
            matched_elements = page_result['matched_elements']
            
            # Calculate page size based on elements
            min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
            
            for element in matched_elements:
                path_info = element['path_info']
                bbox_str = path_info['bounding_box']
                
                coords = bbox_str.replace('Rect(', '').replace(')', '').split(', ')
                if len(coords) >= 4:
                    x1, y1, x2, y2 = map(float, coords[:4])
                    min_x = min(min_x, x1, x2)
                    min_y = min(min_y, y1, y2)
                    max_x = max(max_x, x1, x2)
                    max_y = max(max_y, y1, y2)
            
            # Add padding
            padding = 20
            page_width = max_x - min_x + 2 * padding
            page_height = max_y - min_y + 2 * padding
            
            # Create new PDF
            doc = fitz.open()
            page = doc.new_page(width=page_width, height=page_height)
            
            # Adjust coordinates for padding
            offset_x = padding - min_x
            offset_y = padding - min_y
            
            # Draw CutContour elements
            for element in matched_elements:
                path_info = element['path_info']
                line_width = path_info['line_width']
                
                # Draw in black for cutting paths
                color = (0, 0, 0)  # Black
                
                for item in path_info['items']:
                    if item[0] == 'l':  # Line
                        x1, y1 = map(float, item[1].replace('Point(', '').replace(')', '').split(', '))
                        x2, y2 = map(float, item[2].replace('Point(', '').replace(')', '').split(', '))
                        
                        # Adjust coordinates
                        x1 += offset_x
                        y1 += offset_y
                        x2 += offset_x
                        y2 += offset_y
                        
                        # Draw line
                        page.draw_line(fitz.Point(x1, y1), fitz.Point(x2, y2), 
                                     color=color, width=max(line_width, 0.5))
            
            # Save shapes PDF
            shapes_filename = f"{pdf_name}_cutcontour_shapes_page_{page_num}.pdf"
            shapes_path = os.path.join(output_dir, shapes_filename)
            
            doc.save(shapes_path)
            doc.close()
            
            if self.debug:
                print(f"  ✂️ Generated shapes PDF: {shapes_filename}")
            
            return shapes_path
            
        except Exception as e:
            if self.debug:
                print(f"  ⚠️ Error generating shapes PDF: {e}")
            return None
    
    def _generate_report(self, results: Dict, output_dir: str, pdf_name: str) -> str:
        """Generate detailed text report."""
        try:
            report_filename = f"{pdf_name}_cutcontour_report.txt"
            report_path = os.path.join(output_dir, report_filename)
            
            with open(report_path, 'w') as f:
                f.write(f"CutContour Extraction Report\n")
                f.write(f"{'=' * 50}\n\n")
                
                f.write(f"Input PDF: {results['input_path']}\n")
                f.write(f"Total Pages: {results['total_pages']}\n")
                f.write(f"Pages with CutContour: {results['cutcontour_pages']}\n\n")
                
                f.write(f"Target Colors Searched:\n")
                for color in results['target_colors']:
                    f.write(f"  - {color}\n")
                f.write("\n")
                
                # Page-by-page analysis
                for page_result in results['page_results']:
                    if not page_result['has_cutcontour']:
                        continue
                    
                    page_num = page_result['page']
                    f.write(f"Page {page_num} Analysis\n")
                    f.write(f"{'-' * 20}\n")
                    
                    # Spot color analysis
                    spot_analysis = page_result['spot_color_analysis']
                    f.write(f"Found Target Colors: {len(spot_analysis['found_target_colors'])}\n")
                    for color in spot_analysis['found_target_colors']:
                        f.write(f"  - {color['color_name']} ({color['name']})\n")
                    
                    # Geometric analysis
                    geo_analysis = page_result['geometric_analysis']
                    f.write(f"\nGeometric Analysis:\n")
                    f.write(f"  Total Paths: {geo_analysis['total_paths']}\n")
                    f.write(f"  Potential CutContour Paths: {len(geo_analysis['potential_cutcontour_paths'])}\n")
                    
                    # Matched elements
                    matched_elements = page_result['matched_elements']
                    f.write(f"\nMatched CutContour Elements: {len(matched_elements)}\n")
                    
                    for i, element in enumerate(matched_elements, 1):
                        path_info = element['path_info']
                        f.write(f"\n  Element {i}:\n")
                        f.write(f"    Line Width: {path_info['line_width']}pt\n")
                        f.write(f"    Bounding Box: {path_info['bounding_box']}\n")
                        f.write(f"    Path Type: {path_info['path_type']}\n")
                        f.write(f"    Confidence: {element['match_confidence']}\n")
                        f.write(f"    Reason: {element['match_reason']}\n")
                    
                    f.write(f"\nSummary:\n")
                    summary = page_result['summary']
                    f.write(f"  Confidence: {summary['confidence']}\n")
                    f.write(f"  Target Colors Found: {summary['target_colors_found']}\n")
                    f.write(f"  Matched Elements: {summary['matched_elements']}\n")
                    f.write("\n")
            
            if self.debug:
                print(f"  📋 Generated report: {report_filename}")
            
            return report_path
            
        except Exception as e:
            if self.debug:
                print(f"  ⚠️ Error generating report: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description='Visualize CutContour extraction results')
    parser.add_argument('results_json', help='Path to CutContour extraction results JSON file')
    parser.add_argument('--svg', action='store_true', help='Generate SVG visualization')
    parser.add_argument('--pdf', action='store_true', help='Generate PDF with cutcontour overlay')
    parser.add_argument('--shapes', action='store_true', help='Generate shape-only PDF')
    parser.add_argument('--report', action='store_true', help='Generate detailed text report')
    parser.add_argument('--all', action='store_true', help='Generate all output types')
    parser.add_argument('--output-dir', default='cutcontour_output', help='Output directory')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # If --all is specified, enable all output types
    if args.all:
        args.svg = True
        args.pdf = True
        args.shapes = True
        args.report = True
    
    # If no specific output type is specified, default to SVG and report
    if not any([args.svg, args.pdf, args.shapes, args.report]):
        args.svg = True
        args.report = True
    
    visualizer = CutContourVisualizer(debug=args.debug)
    
    try:
        results = visualizer.visualize_cutcontour(
            results_path=args.results_json,
            output_dir=args.output_dir,
            generate_svg=args.svg,
            generate_pdf=args.pdf,
            generate_shapes=args.shapes,
            generate_report=args.report
        )
        
        print(f"\n📊 CutContour Visualization Summary:")
        print(f"   Input: {results['input_pdf']}")
        print(f"   Output Directory: {results['output_directory']}")
        print(f"   Pages with CutContour: {results['summary']['cutcontour_pages']}/{results['summary']['total_pages']}")
        print(f"   Total Matched Elements: {results['summary']['total_matched_elements']}")
        print(f"   Generated Files: {len(results['generated_files'])}")
        
        for file_path in results['generated_files']:
            print(f"     - {os.path.basename(file_path)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())