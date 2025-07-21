from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from typing import Dict, List
import re


class PreciseCutContourOnlyRemover:
    """
    Precisely removes ONLY the CutContour elements while preserving all design content
    including XObjects like /XO2 Do
    """
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_precisely(self, input_path: str, output_path: str) -> Dict:
        """
        Remove only CutContour color and paths, preserve everything else including design XObjects
        """
        result = {
            'success': False,
            'cutcontour_colorspaces_removed': 0,
            'cutcontour_sequences_removed': 0,
            'design_objects_preserved': 0,
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
                
                # Remove CutContour color space
                self._remove_cutcontour_colorspace(page, result)
                
                # Remove only CutContour paths, preserve design content
                self._remove_cutcontour_paths_only(page, result)
                
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
        Remove CutContour color space definition
        """
        try:
            if '/Resources' not in page or '/ColorSpace' not in page['/Resources']:
                return
                
            color_spaces = page['/Resources']['/ColorSpace']
            cutcontour_cs_name = None
            
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
            
            if cutcontour_cs_name:
                del color_spaces[cutcontour_cs_name]
                if self.debug:
                    print(f"Removed color space: {cutcontour_cs_name}")
                    
        except Exception as e:
            if self.debug:
                print(f"Error removing color space: {e}")
    
    def _remove_cutcontour_paths_only(self, page, result: Dict):
        """
        Remove ONLY CutContour paths while preserving design content like /XO2 Do
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            if hasattr(contents, 'get_object'):
                contents = contents.get_object()
                
            if hasattr(contents, 'get_data'):
                original_content = contents.get_data().decode('latin-1')
                lines = original_content.split('\n')
                result['total_lines_before'] = len(lines)
                
                if self.debug:
                    print(f"Original content has {len(lines)} lines")
                
                # Filter only CutContour sequences, preserve everything else
                filtered_lines = self._filter_only_cutcontour_sequences(lines, result)
                result['total_lines_after'] = len(filtered_lines)
                
                if self.debug:
                    print(f"After filtering: {len(filtered_lines)} lines")
                
                if len(filtered_lines) != len(lines):
                    new_content = '\n'.join(filtered_lines)
                    
                    # Try using set_data method instead of _data assignment
                    if hasattr(contents, 'set_data'):
                        contents.set_data(new_content.encode('latin-1'))
                        if self.debug:
                            print(f"Content updated using set_data: {len(original_content)} -> {len(new_content)} chars")
                    else:
                        # Fallback to manual method
                        contents.update({})
                        contents._data = new_content.encode('latin-1')
                        if self.debug:
                            print(f"Content updated using _data: {len(original_content)} -> {len(new_content)} chars")
                    
                    # Verify the update worked
                    if hasattr(contents, 'get_data'):
                        verification_data = contents.get_data()
                        if self.debug:
                            print(f"Verification: {len(verification_data)} bytes in content stream")
                        
        except Exception as e:
            if self.debug:
                print(f"Error processing content: {e}")
    
    def _filter_only_cutcontour_sequences(self, lines: List[str], result: Dict) -> List[str]:
        """
        Remove ONLY the CutContour drawing sequences, preserve ALL other content
        
        This will:
        1. Keep design content like /XO2 Do 
        2. Keep graphics state commands (q, Q)
        3. Keep clipping and setup commands
        4. Remove ONLY: /Cs3 CS + color + path + stroke
        """
        filtered_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Preserve design content explicitly
            if self._is_design_content(line):
                filtered_lines.append(lines[i])
                result['design_objects_preserved'] += 1
                if self.debug:
                    print(f"PRESERVING design content: {line}")
                i += 1
                continue
            
            # Check for CutContour color setting
            if '/Cs3 CS' in line:
                if self.debug:
                    print(f"Found CutContour color setting at line {i}: {line}")
                
                # Look for the complete CutContour sequence
                sequence_end = self._find_cutcontour_sequence_end(lines, i)
                
                if sequence_end > i:
                    # Remove only this sequence
                    lines_removed = sequence_end - i + 1
                    result['cutcontour_sequences_removed'] += 1
                    
                    if self.debug:
                        print(f"Removing CutContour sequence (lines {i}-{sequence_end}):")
                        for j in range(i, min(sequence_end + 1, i + 8)):
                            print(f"  Remove: {lines[j].strip()}")
                        if sequence_end - i > 7:
                            print(f"  ... and {sequence_end - i - 7} more lines")
                    
                    # Skip only the CutContour sequence
                    i = sequence_end + 1
                    continue
                else:
                    # Incomplete sequence, keep it to be safe
                    filtered_lines.append(lines[i])
            else:
                # Not a CutContour line, keep it
                filtered_lines.append(lines[i])
            
            i += 1
        
        return filtered_lines
    
    def _is_design_content(self, line: str) -> bool:
        """
        Identify lines that contain design content that must be preserved
        """
        line = line.strip()
        
        # XObjects (design content)
        if re.match(r'/XO\d+ Do', line):
            return True
            
        # Image objects
        if re.match(r'/Im\d+ Do', line):
            return True
            
        # Form XObjects
        if line.endswith(' Do') and line.startswith('/'):
            return True
            
        return False
    
    def _find_cutcontour_sequence_end(self, lines: List[str], start_idx: int) -> int:
        """
        Find the end of a CutContour sequence starting from /Cs3 CS
        """
        if start_idx >= len(lines) - 1:
            return -1
            
        # Look for the pattern: /Cs3 CS -> color value -> path -> stroke
        i = start_idx + 1
        found_color = False
        found_path = False
        
        while i < len(lines) and i < start_idx + 20:  # Reasonable limit
            line = lines[i].strip()
            
            # Look for color value (1 SCN)
            if re.match(r'^[\d.\s]+SCN\s*$', line) and not found_color:
                found_color = True
                if self.debug:
                    print(f"  Found color value: {line}")
            
            # Look for path commands
            elif (re.match(r'^[\d.\-\s]+[mlc]\s*$', line) or 
                  line == 'h' or 
                  re.match(r'^[\d.\-\s]*$', line)):
                found_path = True
            
            # Look for stroke command
            elif line in ['S', 's']:
                if found_color:
                    if self.debug:
                        print(f"  Found stroke: {line}")
                    return i
                else:
                    return -1  # Stroke without our color
            
            # Other drawing commands might end our sequence
            elif line in ['f', 'F', 'f*', 'F*', 'B', 'b', 'B*', 'b*', 'n']:
                if found_color:
                    return i
                else:
                    return -1
            
            # Graphics state or other commands
            elif line in ['q', 'Q'] or line.endswith(' gs') or '/' in line:
                # These don't break our sequence, continue
                pass
            
            i += 1
        
        return -1  # Sequence not found
    
    def verify_result(self, pdf_path: str) -> Dict:
        """
        Verify the precise removal results
        """
        try:
            reader = PdfReader(pdf_path)
            page = reader.pages[0]
            
            verification = {
                'has_content': '/Contents' in page,
                'cutcontour_colorspaces': 0,
                'cutcontour_references': 0,
                'design_objects_found': 0,
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
                    
                    # Check for CutContour references
                    if 'CutContour' in content_text or '/Cs3' in content_text:
                        verification['cutcontour_references'] += 1
                    
                    # Check for design objects
                    for line in lines:
                        if re.search(r'/XO\d+ Do|/Im\d+ Do', line):
                            verification['design_objects_found'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}