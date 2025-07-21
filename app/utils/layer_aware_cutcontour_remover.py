from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from typing import Dict, List, Tuple
import re


class LayerAwareCutContourRemover:
    """
    Layer-aware CutContour removal that handles graphics states and layers properly
    """
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_with_layers(self, input_path: str, output_path: str) -> Dict:
        """
        Remove CutContour including its graphics state/layer context
        """
        result = {
            'success': False,
            'cutcontour_colorspaces_removed': 0,
            'cutcontour_layers_removed': 0,
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
                
                # Remove CutContour layer/graphics state context
                self._remove_cutcontour_layer_context(page, result)
                
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
    
    def _remove_cutcontour_layer_context(self, page, result: Dict):
        """
        Remove the complete CutContour layer/graphics state context
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
                
                # Find and remove CutContour layer context
                filtered_lines = self._filter_cutcontour_layer_context(lines, result)
                result['total_lines_after'] = len(filtered_lines)
                
                if self.debug:
                    print(f"After filtering: {len(filtered_lines)} lines")
                
                if len(filtered_lines) != len(lines):
                    new_content = '\n'.join(filtered_lines)
                    new_data = new_content.encode('latin-1')
                    
                    contents.update({})
                    contents._data = new_data
                    
                    if self.debug:
                        print(f"Content updated: {len(original_content)} -> {len(new_content)} chars")
                        
        except Exception as e:
            if self.debug:
                print(f"Error processing content: {e}")
    
    def _filter_cutcontour_layer_context(self, lines: List[str], result: Dict) -> List[str]:
        """
        Remove the complete CutContour layer context including graphics states
        
        Pattern identified:
        q (line 33 - start graphics state)
        [clipping and graphics state setup]
        /GS1 gs /GS3 gs (overprint settings)
        /Cs3 CS (CutContour color space)
        1 SCN (color value)  
        [circle path]
        S (stroke)
        Q Q Q (end graphics states - lines 52-54)
        """
        filtered_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for the graphics state that contains CutContour
            if self._is_cutcontour_graphics_state_start(lines, i):
                if self.debug:
                    print(f"Found CutContour graphics state start at line {i}")
                
                # Find the complete graphics state block
                state_end = self._find_cutcontour_graphics_state_end(lines, i)
                
                if state_end > i:
                    lines_removed = state_end - i + 1
                    result['cutcontour_layers_removed'] += 1
                    
                    if self.debug:
                        print(f"Removing CutContour layer context (lines {i}-{state_end}):")
                        for j in range(i, min(state_end + 1, i + 10)):
                            print(f"  Remove: Line {j}: {lines[j].strip()}")
                        if state_end - i > 9:
                            print(f"  ... and {state_end - i - 9} more lines")
                    
                    # Skip the entire graphics state block
                    i = state_end + 1
                    continue
                else:
                    # Not the pattern we're looking for
                    filtered_lines.append(lines[i])
            else:
                # Keep this line
                filtered_lines.append(lines[i])
            
            i += 1
        
        return filtered_lines
    
    def _is_cutcontour_graphics_state_start(self, lines: List[str], start_idx: int) -> bool:
        """
        Check if this is the start of a graphics state that contains CutContour
        
        Looking for the pattern:
        q (graphics state start)
        [setup commands including clipping, graphics states]
        /GS1 gs /GS3 gs (overprint settings)
        /Cs3 CS (CutContour usage)
        """
        if start_idx >= len(lines) - 10:  # Need at least 10 lines to check pattern
            return False
            
        if lines[start_idx].strip() != 'q':
            return False
            
        # Look ahead for CutContour usage within reasonable distance
        for i in range(start_idx + 1, min(start_idx + 20, len(lines))):
            line = lines[i].strip()
            if '/Cs3 CS' in line:  # Found CutContour color space usage
                # Verify this is the right graphics state by checking for overprint settings
                for j in range(start_idx + 1, i):
                    if '/GS1 gs' in lines[j] or '/GS3 gs' in lines[j]:
                        if self.debug:
                            print(f"  Confirmed CutContour graphics state: found overprint at line {j}")
                        return True
                return False
                
        return False
    
    def _find_cutcontour_graphics_state_end(self, lines: List[str], start_idx: int) -> int:
        """
        Find the end of the CutContour graphics state block
        
        Looking for the pattern after the stroke command:
        S (stroke the CutContour)
        Q Q Q (multiple graphics state endings)
        """
        if start_idx >= len(lines):
            return -1
            
        # First find the stroke command for CutContour
        stroke_found = False
        stroke_idx = -1
        
        for i in range(start_idx + 1, min(start_idx + 25, len(lines))):
            line = lines[i].strip()
            
            # Look for CutContour color setting first
            if '/Cs3 CS' in line:
                # Then look for the stroke command after CutContour path
                for j in range(i + 1, min(i + 15, len(lines))):
                    if lines[j].strip() == 'S':
                        stroke_found = True
                        stroke_idx = j
                        if self.debug:
                            print(f"  Found CutContour stroke at line {j}")
                        break
                break
        
        if not stroke_found:
            return -1
            
        # Now find the matching Q commands after the stroke
        q_count = 1  # We started with one 'q'
        for i in range(stroke_idx + 1, min(stroke_idx + 10, len(lines))):
            line = lines[i].strip()
            if line == 'Q':
                q_count -= 1
                if self.debug:
                    print(f"  Found Q at line {i}, remaining q_count: {q_count}")
                if q_count == 0:
                    # Found all matching Q commands
                    if self.debug:
                        print(f"  Graphics state ends at line {i}")
                    return i
            elif line == 'q':
                q_count += 1
            elif line and not line.startswith('.'):  # Non-empty, non-numeric line
                # Reached content that's not part of the graphics state cleanup
                break
                
        return -1
    
    def verify_result(self, pdf_path: str) -> Dict:
        """
        Verify the layer removal results
        """
        try:
            reader = PdfReader(pdf_path)
            page = reader.pages[0]
            
            verification = {
                'has_content': '/Contents' in page,
                'cutcontour_colorspaces': 0,
                'cutcontour_references': 0,
                'total_content_lines': 0,
                'overprint_references': 0
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
                        
                    # Check for overprint graphics states (should be gone if we removed the layer)
                    if '/GS1 gs' in content_text or '/GS3 gs' in content_text:
                        verification['overprint_references'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}