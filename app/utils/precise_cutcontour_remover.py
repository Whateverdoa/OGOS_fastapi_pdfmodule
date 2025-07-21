from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from typing import Dict, List
import re


class PreciseCutContourRemover:
    """
    Precisely removes CutContour dieline paths based on actual PDF structure analysis
    """
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_dieline(self, input_path: str, output_path: str) -> Dict:
        """
        Remove CutContour dieline based on precise pattern matching
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            Dict with removal results
        """
        result = {
            'success': False,
            'cutcontour_colorspaces_removed': 0,
            'cutcontour_sequences_removed': 0,
            'lines_removed': 0,
            'error': None
        }
        
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Remove CutContour color spaces
                self._remove_cutcontour_colorspaces(page, result)
                
                # Remove CutContour path sequences from content
                self._remove_cutcontour_sequences(page, result)
                
                writer.add_page(page)
            
            # Write the cleaned PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            result['success'] = True
            return result
            
        except Exception as e:
            result['error'] = str(e)
            if self.debug:
                print(f"Error: {e}")
            return result
    
    def _remove_cutcontour_colorspaces(self, page, result: Dict):
        """
        Remove CutContour color space definitions
        """
        try:
            if '/Resources' not in page or '/ColorSpace' not in page['/Resources']:
                return
                
            color_spaces = page['/Resources']['/ColorSpace']
            spaces_to_remove = []
            
            for cs_name, cs_def in color_spaces.items():
                if self._is_cutcontour_colorspace(cs_def):
                    spaces_to_remove.append(cs_name)
                    result['cutcontour_colorspaces_removed'] += 1
                    if self.debug:
                        print(f"Found CutContour color space: {cs_name}")
            
            # Remove identified color spaces
            for cs_name in spaces_to_remove:
                del color_spaces[cs_name]
                if self.debug:
                    print(f"Removed color space: {cs_name}")
                    
        except Exception as e:
            if self.debug:
                print(f"Error removing color spaces: {e}")
    
    def _remove_cutcontour_sequences(self, page, result: Dict):
        """
        Remove CutContour path sequences from content streams
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            
            if isinstance(contents, list):
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    self._process_content_stream(content_stream, result)
            else:
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                self._process_content_stream(contents, result)
                
        except Exception as e:
            if self.debug:
                print(f"Error processing content streams: {e}")
    
    def _process_content_stream(self, content_stream, result: Dict):
        """
        Process a single content stream to remove CutContour sequences
        """
        try:
            if not hasattr(content_stream, 'get_data'):
                return
                
            content_data = content_stream.get_data()
            content_text = content_data.decode('latin-1')
            
            # Find and remove CutContour sequences
            filtered_text = self._filter_cutcontour_sequences(content_text, result)
            
            # Update content stream if changes were made
            if filtered_text != content_text:
                try:
                    new_data = filtered_text.encode('latin-1')
                    content_stream.update({})  # Force decode
                    content_stream._data = new_data
                    if self.debug:
                        print(f"Updated content stream ({len(content_text)} -> {len(filtered_text)} chars)")
                except Exception as e:
                    if self.debug:
                        print(f"Error updating content stream: {e}")
                        
        except Exception as e:
            if self.debug:
                print(f"Error processing content stream: {e}")
    
    def _filter_cutcontour_sequences(self, content_text: str, result: Dict) -> str:
        """
        Filter out CutContour sequences based on the pattern:
        /Cs3 CS (or similar CutContour colorspace)
        1 SCN (color value)
        path data...
        S (stroke command)
        """
        lines = content_text.split('\n')
        filtered_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if this line sets a CutContour color space
            cutcontour_cs_match = self._find_cutcontour_colorspace_usage(line)
            
            if cutcontour_cs_match:
                # Found start of CutContour sequence
                if self.debug:
                    print(f"Found CutContour color space usage: {line}")
                
                # Look for the complete sequence
                sequence_start = i
                sequence_end = self._find_cutcontour_sequence_end(lines, i)
                
                if sequence_end > i:
                    # Found complete sequence
                    lines_removed = sequence_end - i + 1
                    result['cutcontour_sequences_removed'] += 1
                    result['lines_removed'] += lines_removed
                    
                    if self.debug:
                        print(f"Removing CutContour sequence (lines {sequence_start}-{sequence_end}):")
                        for j in range(sequence_start, min(sequence_end + 1, sequence_start + 10)):
                            print(f"  Removing: {lines[j].strip()}")
                        if sequence_end - sequence_start > 9:
                            print(f"  ... and {sequence_end - sequence_start - 9} more lines")
                    
                    # Skip the entire sequence
                    i = sequence_end + 1
                    continue
                else:
                    # Incomplete sequence, keep the line
                    filtered_lines.append(lines[i])
            else:
                # Not a CutContour line, keep it
                filtered_lines.append(lines[i])
            
            i += 1
        
        return '\n'.join(filtered_lines)
    
    def _find_cutcontour_colorspace_usage(self, line: str) -> bool:
        """
        Check if line sets a CutContour color space (like /Cs3 CS)
        We need to identify which color space names are CutContour
        """
        # Look for color space setting patterns
        cs_pattern = r'/Cs\d+\s+CS'  # Matches /Cs3 CS, /Cs1 CS, etc.
        return bool(re.search(cs_pattern, line))
    
    def _find_cutcontour_sequence_end(self, lines: List[str], start_idx: int) -> int:
        """
        Find the end of a CutContour sequence starting from start_idx
        Looking for the pattern: colorspace -> color value -> path data -> stroke
        """
        i = start_idx + 1
        found_color_value = False
        found_path_data = False
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for color value setting (like "1 SCN")
            if re.match(r'^[\d\.\s]+SCN\s*$', line) and not found_color_value:
                found_color_value = True
                if self.debug:
                    print(f"  Found color value: {line}")
            
            # Look for path construction commands
            elif (re.match(r'^[\d\.\-\s]+[mlc]\s*$', line) or  # moveto, lineto, curveto
                  line == 'h' or  # closepath
                  re.match(r'^[\d\.\-\s]*$', line)):  # coordinate data
                found_path_data = True
                if self.debug and not found_path_data:
                    print(f"  Found path data starting: {line}")
            
            # Look for drawing commands that end the sequence
            elif line in ['S', 's', 'f', 'F', 'f*', 'F*', 'B', 'b', 'B*', 'b*']:
                if found_color_value:  # Only if we found color value
                    if self.debug:
                        print(f"  Found drawing command: {line}")
                    return i  # End of sequence
                else:
                    # Drawing command without color value, not our sequence
                    return start_idx  # Invalid sequence
            
            # Look for state change commands that might end the sequence
            elif line in ['Q', 'q']:
                # Graphics state change - might be end of sequence
                if found_color_value and found_path_data:
                    return i - 1  # End before the state change
            
            # Other unrecognized commands might indicate end of our sequence
            elif not re.match(r'^[\d\.\-\s]*$', line) and line not in ['h']:
                if found_color_value:
                    return i - 1  # End before this unknown command
                else:
                    return start_idx  # Invalid sequence
            
            i += 1
        
        # Reached end of content
        return start_idx  # Incomplete sequence
    
    def _is_cutcontour_colorspace(self, cs_def) -> bool:
        """
        Check if color space definition contains CutContour
        """
        try:
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()
                
            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__') and len(cs_def) > 1:
                if str(cs_def[0]) == '/Separation':
                    color_name = str(cs_def[1]).replace('/', '')
                    return color_name.lower() == 'cutcontour'
        except:
            pass
            
        return 'CutContour' in str(cs_def)
    
    def verify_removal(self, pdf_path: str) -> Dict:
        """
        Verify CutContour removal
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'pages_checked': len(reader.pages),
                'cutcontour_colorspaces_found': 0,
                'cutcontour_content_references': 0,
                'has_content': True
            }
            
            for page in reader.pages:
                # Check color spaces
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    color_spaces = page['/Resources']['/ColorSpace']
                    for cs_name, cs_def in color_spaces.items():
                        if self._is_cutcontour_colorspace(cs_def):
                            verification['cutcontour_colorspaces_found'] += 1
                
                # Check content for CutContour references
                if '/Contents' in page:
                    contents = page['/Contents']
                    if isinstance(contents, list):
                        for content_stream in contents:
                            if hasattr(content_stream, 'get_object'):
                                content_stream = content_stream.get_object()
                            if hasattr(content_stream, 'get_data'):
                                content_text = content_stream.get_data().decode('latin-1', errors='ignore')
                                if 'CutContour' in content_text:
                                    verification['cutcontour_content_references'] += 1
                    else:
                        if hasattr(contents, 'get_object'):
                            contents = contents.get_object()
                        if hasattr(contents, 'get_data'):
                            content_text = contents.get_data().decode('latin-1', errors='ignore')
                            if 'CutContour' in content_text:
                                verification['cutcontour_content_references'] += 1
                else:
                    verification['has_content'] = False
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}