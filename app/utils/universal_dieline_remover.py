from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from typing import Dict, List, Set
import re


class UniversalDielineRemover:
    """
    Universal dieline remover for circles and rectangles
    Removes any dieline spot color while preserving design content
    """
    
    # Complete list of dieline spot colors to target
    TARGET_DIELINE_COLORS = [
        # CutContour variations
        'CutContour', 'cutcontour', 'CUTCONTOUR',
        'Cut Contour', 'cut contour', 'CUT CONTOUR',
        'Cut_Contour', 'cut_contour', 'CUT_CONTOUR',
        
        # KissCut variations  
        'KissCut', 'kisscut', 'KISSCUT',
        'Kiss Cut', 'kiss cut', 'KISS CUT',
        'Kiss_Cut', 'kiss_cut', 'KISS_CUT',
        
        # Stans (Dutch for dieline)
        'stans', 'Stans', 'STANS',
        'stanslijn', 'Stanslijn', 'STANSLIJN',
        
        # DieCut variations
        'DieCut', 'diecut', 'DIECUT', 
        'Die Cut', 'die cut', 'DIE CUT',
        'Die_Cut', 'die_cut', 'DIE_CUT',
        
        # Other common dieline names
        'dieline', 'Dieline', 'DIELINE',
        'cut', 'Cut', 'CUT',
        'knife', 'Knife', 'KNIFE',
        'perf', 'Perf', 'PERF',
        'crease', 'Crease', 'CREASE'
    ]
    
    def __init__(self):
        self.debug = False
        self.found_dieline_colors = set()
        self.found_dieline_colorspaces = {}
        
    def remove_dielines_from_shapes(self, input_path: str, output_path: str, shape_type: str) -> Dict:
        """
        Remove dielines from circle or rectangle shapes
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path  
            shape_type: 'circle' or 'rectangle'
            
        Returns:
            Dict with removal results
        """
        result = {
            'success': False,
            'shape_type': shape_type,
            'dieline_colorspaces_removed': 0,
            'dieline_sequences_removed': 0,
            'design_objects_preserved': 0,
            'dieline_colors_found': [],
            'total_lines_before': 0,
            'total_lines_after': 0,
            'error': None
        }
        
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1} for {shape_type} dieline removal")
                
                # Step 1: Find all dieline color spaces
                self._find_dieline_colorspaces(page, result)
                
                # Step 2: Remove dieline color spaces
                self._remove_dieline_colorspaces(page, result)
                
                # Step 3: Remove dieline paths from content
                self._remove_dieline_paths_from_content(page, result)
                
                writer.add_page(page)
            
            # Write result
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            result['success'] = True
            result['dieline_colors_found'] = list(self.found_dieline_colors)
            return result
            
        except Exception as e:
            result['error'] = str(e)
            if self.debug:
                print(f"Error: {e}")
            return result
    
    def _find_dieline_colorspaces(self, page, result: Dict):
        """
        Find all dieline color spaces in the page
        """
        try:
            if '/Resources' not in page or '/ColorSpace' not in page['/Resources']:
                return
                
            color_spaces = page['/Resources']['/ColorSpace']
            
            for cs_name, cs_def in color_spaces.items():
                dieline_color = self._identify_dieline_colorspace(cs_name, cs_def)
                if dieline_color:
                    self.found_dieline_colors.add(dieline_color)
                    self.found_dieline_colorspaces[cs_name] = dieline_color
                    if self.debug:
                        print(f"Found dieline color space: {cs_name} -> {dieline_color}")
                    
        except Exception as e:
            if self.debug:
                print(f"Error finding dieline color spaces: {e}")
    
    def _identify_dieline_colorspace(self, cs_name: str, cs_def) -> str:
        """
        Check if a color space is a dieline and return the dieline color name
        """
        try:
            # Handle IndirectObject references
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()
                
            # Convert to string for analysis
            cs_def_str = str(cs_def)
            
            # Check for Separation color space with dieline colors
            if (hasattr(cs_def, '__getitem__') and 
                hasattr(cs_def, '__len__') and 
                len(cs_def) > 1 and 
                str(cs_def[0]) == '/Separation'):
                
                # Get the color name
                color_name = str(cs_def[1]).replace('/', '').strip()
                
                # Check against target dieline colors
                for target_color in self.TARGET_DIELINE_COLORS:
                    if color_name.lower() == target_color.lower():
                        return target_color
            
            # Also check the full definition string for dieline color names
            for target_color in self.TARGET_DIELINE_COLORS:
                if f"'/{target_color}'" in cs_def_str or f'"{target_color}"' in cs_def_str:
                    return target_color
                    
        except Exception as e:
            if self.debug:
                print(f"Error identifying colorspace {cs_name}: {e}")
            
        return None
    
    def _remove_dieline_colorspaces(self, page, result: Dict):
        """
        Remove dieline color space definitions
        """
        try:
            if '/Resources' not in page or '/ColorSpace' not in page['/Resources']:
                return
                
            color_spaces = page['/Resources']['/ColorSpace']
            
            # Remove all found dieline color spaces
            for cs_name in list(self.found_dieline_colorspaces.keys()):
                if cs_name in color_spaces:
                    del color_spaces[cs_name]
                    result['dieline_colorspaces_removed'] += 1
                    if self.debug:
                        print(f"Removed dieline color space: {cs_name}")
                    
        except Exception as e:
            if self.debug:
                print(f"Error removing dieline color spaces: {e}")
    
    def _remove_dieline_paths_from_content(self, page, result: Dict):
        """
        Remove dieline paths from content streams while preserving design
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
                
                # Filter out dieline sequences, preserve everything else
                filtered_lines = self._filter_dieline_sequences(lines, result)
                result['total_lines_after'] = len(filtered_lines)
                
                if self.debug:
                    print(f"After filtering: {len(filtered_lines)} lines")
                
                if len(filtered_lines) != len(lines):
                    new_content = '\n'.join(filtered_lines)
                    
                    # Update content stream using set_data method
                    if hasattr(contents, 'set_data'):
                        contents.set_data(new_content.encode('latin-1'))
                        if self.debug:
                            print(f"Content updated: {len(original_content)} -> {len(new_content)} chars")
                    
                    # Verify the update worked
                    if hasattr(contents, 'get_data'):
                        verification_data = contents.get_data()
                        if self.debug:
                            print(f"Verification: {len(verification_data)} bytes in content stream")
                        
        except Exception as e:
            if self.debug:
                print(f"Error processing content: {e}")
    
    def _filter_dieline_sequences(self, lines: List[str], result: Dict) -> List[str]:
        """
        Remove dieline drawing sequences while preserving all design content
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
            
            # Check if this line sets a dieline color space
            dieline_cs_usage = self._find_dieline_colorspace_usage(line)
            
            if dieline_cs_usage:
                if self.debug:
                    print(f"Found dieline color usage at line {i}: {line}")
                
                # Look for the complete dieline sequence
                sequence_end = self._find_dieline_sequence_end(lines, i)
                
                if sequence_end > i:
                    # Remove the dieline sequence
                    lines_removed = sequence_end - i + 1
                    result['dieline_sequences_removed'] += 1
                    
                    if self.debug:
                        print(f"Removing dieline sequence (lines {i}-{sequence_end}):")
                        for j in range(i, min(sequence_end + 1, i + 8)):
                            print(f"  Remove: {lines[j].strip()}")
                        if sequence_end - i > 7:
                            print(f"  ... and {sequence_end - i - 7} more lines")
                    
                    # Skip the entire dieline sequence
                    i = sequence_end + 1
                    continue
                else:
                    # Incomplete sequence, keep it to be safe
                    filtered_lines.append(lines[i])
            else:
                # Not a dieline line, keep it
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
    
    def _find_dieline_colorspace_usage(self, line: str) -> str:
        """
        Check if line uses a dieline color space and return the colorspace name
        """
        line = line.strip()
        
        # Look for color space setting patterns that match our found dieline colorspaces
        for cs_name in self.found_dieline_colorspaces.keys():
            if f'{cs_name} CS' in line or f'{cs_name} cs' in line:
                return cs_name
                
        return None
    
    def _find_dieline_sequence_end(self, lines: List[str], start_idx: int) -> int:
        """
        Find the end of a dieline sequence starting from dieline color space usage
        """
        if start_idx >= len(lines) - 1:
            return -1
            
        i = start_idx + 1
        found_color = False
        found_path = False
        
        while i < len(lines) and i < start_idx + 25:  # Reasonable limit
            line = lines[i].strip()
            
            # Look for color value (like "1 SCN")
            if re.match(r'^[\d.\s]+SCN\s*$', line) and not found_color:
                found_color = True
                if self.debug:
                    print(f"  Found color value: {line}")
            
            # Look for path commands
            elif (re.match(r'^[\d.\-\s]+[mlc]\s*$', line) or 
                  line == 'h' or 
                  re.match(r'^[\d.\-\s]*$', line)):
                found_path = True
            
            # Look for stroke/fill commands that end the sequence
            elif line in ['S', 's', 'f', 'F', 'f*', 'F*', 'B', 'b', 'B*', 'b*', 'n']:
                if found_color:
                    if self.debug:
                        print(f"  Found drawing command: {line}")
                    return i
                else:
                    return -1  # Drawing without our color
            
            # Graphics state changes
            elif line in ['q', 'Q'] or line.endswith(' gs'):
                # These don't necessarily break our sequence
                pass
            
            # Other commands might break the sequence
            elif not re.match(r'^[\d.\-\s]*$', line) and line not in ['h']:
                if found_color:
                    return i - 1  # End before this command
                else:
                    return -1  # Invalid sequence
            
            i += 1
        
        return -1  # Sequence not found
    
    def verify_removal(self, pdf_path: str) -> Dict:
        """
        Verify the dieline removal results
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'pages_checked': len(reader.pages),
                'dieline_colorspaces_found': 0,
                'dieline_content_references': 0,
                'design_objects_found': 0,
                'total_content_lines': 0,
                'remaining_dieline_colors': []
            }
            
            for page in reader.pages:
                # Check for remaining dieline color spaces
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    color_spaces = page['/Resources']['/ColorSpace']
                    for cs_name, cs_def in color_spaces.items():
                        dieline_color = self._identify_dieline_colorspace(cs_name, cs_def)
                        if dieline_color:
                            verification['dieline_colorspaces_found'] += 1
                            verification['remaining_dieline_colors'].append(dieline_color)
                
                # Check content
                if '/Contents' in page:
                    contents = page['/Contents']
                    if hasattr(contents, 'get_object'):
                        contents = contents.get_object()
                    if hasattr(contents, 'get_data'):
                        content_text = contents.get_data().decode('latin-1', errors='ignore')
                        lines = content_text.split('\n')
                        verification['total_content_lines'] += len([l for l in lines if l.strip()])
                        
                        # Check for dieline references
                        for target_color in self.TARGET_DIELINE_COLORS:
                            if target_color in content_text:
                                verification['dieline_content_references'] += 1
                                break
                        
                        # Check for design objects
                        for line in lines:
                            if re.search(r'/XO\d+ Do|/Im\d+ Do', line):
                                verification['design_objects_found'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}