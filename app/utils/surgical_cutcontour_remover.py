from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from typing import Dict, List
import re


class SurgicalCutContourRemover:
    """
    SURGICAL removal - only removes the exact CutContour dieline sequence
    Based on analysis: /Cs3 CS -> 1 SCN -> circle path -> S
    """
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_only(self, input_path: str, output_path: str) -> Dict:
        """
        Surgically remove ONLY the CutContour dieline, keep everything else
        """
        result = {
            'success': False,
            'cutcontour_colorspaces_removed': 0,
            'cutcontour_paths_removed': 0,
            'total_lines_before': 0,
            'total_lines_after': 0,
            'error': None
        }
        
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Step 1: Remove CutContour color space definition
                self._remove_cutcontour_colorspace(page, result)
                
                # Step 2: Remove ONLY the CutContour path sequence from content
                self._surgically_remove_cutcontour_path(page, result)
                
                writer.add_page(page)
            
            # Write result
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            result['success'] = True
            return result
            
        except Exception as e:
            result['error'] = str(e)
            if self.debug:
                print(f"Error: {e}")
            return result
    
    def _remove_cutcontour_colorspace(self, page, result: Dict):
        """
        Remove only the CutContour color space (/Cs3)
        """
        try:
            if '/Resources' not in page or '/ColorSpace' not in page['/Resources']:
                return
                
            color_spaces = page['/Resources']['/ColorSpace']
            cutcontour_cs_name = None
            
            # Find the CutContour color space
            for cs_name, cs_def in color_spaces.items():
                if hasattr(cs_def, 'get_object'):
                    cs_def = cs_def.get_object()
                    
                if (hasattr(cs_def, '__getitem__') and 
                    len(cs_def) > 1 and 
                    str(cs_def[0]) == '/Separation' and 
                    '/CutContour' in str(cs_def[1])):
                    cutcontour_cs_name = cs_name
                    result['cutcontour_colorspaces_removed'] += 1
                    if self.debug:
                        print(f"Found CutContour color space: {cs_name}")
                    break
            
            # Remove only the CutContour color space
            if cutcontour_cs_name:
                del color_spaces[cutcontour_cs_name]
                if self.debug:
                    print(f"Removed color space: {cutcontour_cs_name}")
                    
        except Exception as e:
            if self.debug:
                print(f"Error removing color space: {e}")
    
    def _surgically_remove_cutcontour_path(self, page, result: Dict):
        """
        Remove ONLY the CutContour path sequence, keep all other content
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            if hasattr(contents, 'get_object'):
                contents = contents.get_object()
                
            if hasattr(contents, 'get_data'):
                original_content = contents.get_data().decode('latin-1')
                lines = original_content.split('\n')  # Fixed: single backslash
                result['total_lines_before'] = len(lines)
                
                if self.debug:
                    print(f"Original content has {len(lines)} lines")
                
                # Filter out ONLY the CutContour sequence
                filtered_lines = self._filter_cutcontour_sequence(lines, result)
                result['total_lines_after'] = len(filtered_lines)
                
                if self.debug:
                    print(f"After filtering: {len(filtered_lines)} lines")
                
                # Update content ONLY if we actually removed something
                if len(filtered_lines) != len(lines):
                    new_content = '\n'.join(filtered_lines)  # Fixed: single backslash
                    new_data = new_content.encode('latin-1')
                    
                    # Update the content stream
                    contents.update({})  # Force decode
                    contents._data = new_data
                    
                    if self.debug:
                        print(f"Content updated: {len(original_content)} -> {len(new_content)} chars")
                else:
                    if self.debug:
                        print("No changes made to content")
                        
        except Exception as e:
            if self.debug:
                print(f"Error processing content: {e}")
    
    def _filter_cutcontour_sequence(self, lines: List[str], result: Dict) -> List[str]:
        """
        Remove ONLY the specific CutContour sequence:
        /Cs3 CS
        1 SCN  
        [circle path coordinates]
        h
        S
        """
        filtered_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for the exact pattern: /Cs3 CS
            if line == '/Cs3 CS':
                if self.debug:
                    print(f"Found CutContour sequence start at line {i}: {line}")
                
                # Look ahead to confirm this is the CutContour circle sequence
                sequence_end = self._find_cutcontour_circle_end(lines, i)
                
                if sequence_end > i:
                    # Found complete CutContour circle - remove it
                    lines_removed = sequence_end - i + 1
                    result['cutcontour_paths_removed'] += 1
                    
                    if self.debug:
                        print(f"Removing CutContour circle (lines {i}-{sequence_end}):")
                        for j in range(i, min(sequence_end + 1, i + 8)):
                            print(f"  Remove: {lines[j].strip()}")
                        if sequence_end - i > 7:
                            print(f"  ... and {sequence_end - i - 7} more lines")
                    
                    # Skip the entire sequence
                    i = sequence_end + 1
                    continue
                else:
                    # Not the pattern we're looking for, keep it
                    if self.debug:
                        print(f"Not CutContour circle pattern, keeping: {line}")
                    filtered_lines.append(lines[i])
            else:
                # Not a CutContour line, keep it
                filtered_lines.append(lines[i])
            
            i += 1
        
        return filtered_lines
    
    def _find_cutcontour_circle_end(self, lines: List[str], start_idx: int) -> int:
        """
        Find the end of the CutContour circle sequence starting from /Cs3 CS
        Expected pattern:
        /Cs3 CS
        1 SCN
        [circle coordinates with moveto/curveto]
        h (closepath)
        S (stroke)
        """
        if start_idx >= len(lines) - 1:
            return -1
            
        # Check next line should be "1 SCN"
        if start_idx + 1 < len(lines) and lines[start_idx + 1].strip() == '1 SCN':
            i = start_idx + 2
            found_circle_coords = False
            
            # Look for circle coordinates (moveto + 4 curveto commands)
            while i < len(lines):
                line = lines[i].strip()
                
                # Check for moveto command (should be first coordinate line)
                if re.match(r'^[\d.\-\s]+m\s*$', line) and not found_circle_coords:
                    found_circle_coords = True
                    if self.debug:
                        print(f"  Found circle start (moveto): {line}")
                
                # Check for curveto commands (circle has 4 of these)
                elif re.match(r'^[\d.\-\s]+c\s*$', line):
                    if self.debug:
                        print(f"  Found curveto: {line}")
                
                # Check for closepath
                elif line == 'h':
                    if self.debug:
                        print(f"  Found closepath: {line}")
                
                # Check for stroke - this should be the end
                elif line == 'S':
                    if found_circle_coords:
                        if self.debug:
                            print(f"  Found stroke (end): {line}")
                        return i  # This is the end of the sequence
                    else:
                        return -1  # Stroke without circle coords, not our pattern
                
                # Any other command breaks the pattern
                elif not re.match(r'^[\d.\-\s]*$', line):  # Not just coordinates
                    return -1  # Unexpected command, not our pattern
                
                i += 1
        
        return -1  # Pattern not found
    
    def verify_result(self, pdf_path: str) -> Dict:
        """
        Verify what's left in the PDF
        """
        try:
            reader = PdfReader(pdf_path)
            page = reader.pages[0]
            
            verification = {
                'has_content': '/Contents' in page,
                'cutcontour_colorspaces': 0,
                'cutcontour_references': 0,
                'total_content_lines': 0
            }
            
            # Check color spaces
            if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                color_spaces = page['/Resources']['/ColorSpace']
                for cs_name, cs_def in color_spaces.items():
                    if 'CutContour' in str(cs_def):
                        verification['cutcontour_colorspaces'] += 1
            
            # Check content
            if '/Contents' in page:
                contents = page['/Contents']
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                if hasattr(contents, 'get_data'):
                    content_text = contents.get_data().decode('latin-1', errors='ignore')
                    lines = content_text.split('\n')
                    verification['total_content_lines'] = len([l for l in lines if l.strip()])
                    
                    if 'CutContour' in content_text or '/Cs3' in content_text:
                        verification['cutcontour_references'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}