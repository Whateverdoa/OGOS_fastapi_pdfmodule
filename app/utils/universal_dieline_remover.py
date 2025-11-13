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

                # Step 1: Collect dieline color spaces on page and nested XObjects
                self._collect_dieline_colorspaces_recursive(page, result)

                # Step 2: Remove dieline color spaces throughout resources tree
                self._remove_dieline_colorspaces_recursive(page, result)

                # Step 3: Remove dieline paths from page content and nested XObjects
                self._remove_dieline_paths_in_contents(page, result)
                
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
    
    def _collect_dieline_colorspaces_recursive(self, obj, result: Dict):
        """Collect dieline ColorSpace names from /Resources on the object and nested XObjects."""
        try:
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()

            if resources and '/ColorSpace' in resources:
                color_spaces = resources['/ColorSpace']
                if hasattr(color_spaces, 'get_object'):
                    color_spaces = color_spaces.get_object()
                if hasattr(color_spaces, 'items'):
                    for cs_name, cs_def in color_spaces.items():
                        dieline_color = self._identify_dieline_colorspace(cs_name, cs_def)
                        if dieline_color:
                            self.found_dieline_colors.add(dieline_color)
                            self.found_dieline_colorspaces[cs_name] = dieline_color
                            if self.debug:
                                print(f"Found dieline color space: {cs_name} -> {dieline_color}")

            # Recurse into XObjects (Forms)
            if resources and '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                if hasattr(xobjs, 'items'):
                    for name, xo in xobjs.items():
                        if hasattr(xo, 'get_object'):
                            xo = xo.get_object()
                        subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                        if subtype == '/Form':
                            self._collect_dieline_colorspaces_recursive(xo, result)
        except Exception as e:
            if self.debug:
                print(f"Error collecting colorspaces recursively: {e}")
    
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
    
    def _remove_dieline_colorspaces_recursive(self, obj, result: Dict):
        """Remove dieline ColorSpace definitions from /Resources on the object and nested XObjects."""
        try:
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()
            if not resources:
                return

            # Remove at this level
            if '/ColorSpace' in resources:
                color_spaces = resources['/ColorSpace']
                if hasattr(color_spaces, 'get_object'):
                    color_spaces = color_spaces.get_object()
                if hasattr(color_spaces, 'keys'):
                    for cs_name in list(color_spaces.keys()):
                        if cs_name in self.found_dieline_colorspaces:
                            del color_spaces[cs_name]
                            result['dieline_colorspaces_removed'] += 1
                            if self.debug:
                                print(f"Removed dieline color space: {cs_name}")

            # Recurse into XObjects (Forms)
            if '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                if hasattr(xobjs, 'items'):
                    for _, xo in xobjs.items():
                        if hasattr(xo, 'get_object'):
                            xo = xo.get_object()
                        subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                        if subtype == '/Form':
                            self._remove_dieline_colorspaces_recursive(xo, result)
        except Exception as e:
            if self.debug:
                print(f"Error removing colorspaces recursively: {e}")
    
    def _remove_dieline_paths_in_contents(self, obj, result: Dict):
        """Remove dieline paths from content streams on the object and nested XObjects."""
        try:
            # Process this object's own stream (Form XObject) or its /Contents
            target = None
            if hasattr(obj, 'get_data'):
                target = obj  # Form XObject stream
            else:
                target = obj.get('/Contents') if hasattr(obj, 'get') else None
                if target and hasattr(target, 'get_object'):
                    target = target.get_object()

            def process_stream(stream_obj):
                if not stream_obj:
                    return
                s = stream_obj
                if hasattr(s, 'get_object'):
                    s = s.get_object()
                if hasattr(s, 'get_data'):
                    try:
                        original_content = s.get_data().decode('latin-1', errors='ignore')
                    except Exception:
                        original_content = ''
                    lines = original_content.split('\n')
                    if len(lines) > result.get('total_lines_before', 0):
                        result['total_lines_before'] = len(lines)

                    filtered_lines = self._filter_dieline_sequences(lines, result)
                    if len(filtered_lines) != len(lines):
                        new_content = '\n'.join(filtered_lines)
                        if hasattr(s, 'set_data'):
                            s.set_data(new_content.encode('latin-1'))
                elif isinstance(s, list):
                    for item in s:
                        process_stream(item)

            if target is not None:
                process_stream(target)

            # Recurse into nested XObjects
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()
            if resources and '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                if hasattr(xobjs, 'items'):
                    for _, xo in xobjs.items():
                        if hasattr(xo, 'get_object'):
                            xo = xo.get_object()
                        subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                        if subtype == '/Form':
                            # Process the form's own stream then recurse
                            self._remove_dieline_paths_in_contents(xo, result)
        except Exception as e:
            if self.debug:
                print(f"Error removing dieline paths in contents: {e}")
    
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

    def remove_registration_marks(self, input_path: str, output_path: str) -> Dict:
        """
        Remove registration/crop marks that use the special Separation color 'All'.

        Strategy: find ColorSpace entries with Separation name 'All' on pages and
        nested Form XObjects; remove their drawing sequences from content streams
        and delete the ColorSpace definitions from resources.
        """
        result = {
            'success': False,
            'registration_colorspaces_removed': 0,
            'registration_sequences_removed': 0,
            'error': None
        }
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()

            for page in reader.pages:
                # Collect registration colorspace names
                reg_cs_names = set()
                self._collect_registration_colorspaces_recursive(page, reg_cs_names)

                if reg_cs_names:
                    # Temporarily direct the content remover to target these cs names
                    self.found_dieline_colorspaces = {name: 'All' for name in reg_cs_names}
                    self._remove_dieline_paths_in_contents(page, result)
                    # Remove the ColorSpace definitions
                    self._remove_specific_colorspaces_recursive(page, reg_cs_names, result)

                writer.add_page(page)

            with open(output_path, 'wb') as f:
                writer.write(f)

            result['success'] = True
            return result
        except Exception as e:
            result['error'] = str(e)
            return result

    def _collect_registration_colorspaces_recursive(self, obj, names_out: Set[str]):
        try:
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()
            if resources and '/ColorSpace' in resources:
                cs = resources['/ColorSpace']
                if hasattr(cs, 'get_object'):
                    cs = cs.get_object()
                for cs_name, cs_def in getattr(cs, 'items', lambda: [])():
                    try:
                        if hasattr(cs_def, 'get_object'):
                            cs_def = cs_def.get_object()
                        if (hasattr(cs_def, '__getitem__') and len(cs_def) > 1 and
                            str(cs_def[0]) == '/Separation'):
                            color_name = str(cs_def[1]).replace('/', '').strip()
                            if color_name.lower() == 'all':
                                names_out.add(cs_name)
                    except Exception:
                        pass
            # Recurse into forms
            if resources and '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                for _, xo in getattr(xobjs, 'items', lambda: [])():
                    if hasattr(xo, 'get_object'):
                        xo = xo.get_object()
                    subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                    if subtype == '/Form':
                        self._collect_registration_colorspaces_recursive(xo, names_out)
        except Exception:
            pass

    def _remove_specific_colorspaces_recursive(self, obj, target_names: Set[str], result: Dict):
        try:
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()
            if resources and '/ColorSpace' in resources:
                cs = resources['/ColorSpace']
                if hasattr(cs, 'get_object'):
                    cs = cs.get_object()
                for name in list(getattr(cs, 'keys', lambda: [])()):
                    if name in target_names:
                        try:
                            del cs[name]
                            result['registration_colorspaces_removed'] = result.get('registration_colorspaces_removed', 0) + 1
                        except Exception:
                            pass
            if resources and '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                for _, xo in getattr(xobjs, 'items', lambda: [])():
                    if hasattr(xo, 'get_object'):
                        xo = xo.get_object()
                    subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                    if subtype == '/Form':
                        self._remove_specific_colorspaces_recursive(xo, target_names, result)
        except Exception:
            pass
    def prune_unwanted_spot_colors(self, input_path: str, output_path: str, allowed_names: Set[str]) -> Dict:
        """
        Remove spot ColorSpace definitions for known dieline colors except those explicitly allowed.

        Args:
            input_path: Input PDF
            output_path: Output PDF
            allowed_names: set of spot color names to keep (case-insensitive compare)

        Returns:
            Dict with counts of removed color spaces.
        """
        result = {
            'success': False,
            'removed_colorspaces': 0,
            'allowed': list(allowed_names),
            'error': None,
        }
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()

            # Normalize allowed set to lowercase for comparison
            allowed_lower = {n.lower() for n in allowed_names}

            for page in reader.pages:
                # Remove from this page and nested XObjects
                self._prune_colorspaces_recursive(page, allowed_lower, result)
                writer.add_page(page)

            with open(output_path, 'wb') as f:
                writer.write(f)

            result['success'] = True
            return result
        except Exception as e:
            result['error'] = str(e)
            return result

    def _prune_colorspaces_recursive(self, obj, allowed_lower: Set[str], result: Dict):
        """Remove ColorSpace entries that match target dieline colors but are not allowed."""
        try:
            resources = obj.get('/Resources') if hasattr(obj, 'get') else None
            if resources and hasattr(resources, 'get_object'):
                resources = resources.get_object()

            # Remove at this level
            if resources and '/ColorSpace' in resources:
                cs = resources['/ColorSpace']
                if hasattr(cs, 'get_object'):
                    cs = cs.get_object()
                if hasattr(cs, 'items'):
                    for cs_name in list(cs.keys()):
                        cs_def = cs.get(cs_name)
                        dieline_color = self._identify_dieline_colorspace(cs_name, cs_def)
                        if dieline_color and dieline_color.lower() not in allowed_lower:
                            del cs[cs_name]
                            result['removed_colorspaces'] += 1

            # Recurse into XObjects
            if resources and '/XObject' in resources:
                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()
                if hasattr(xobjs, 'items'):
                    for _, xo in xobjs.items():
                        if hasattr(xo, 'get_object'):
                            xo = xo.get_object()
                        subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                        if subtype == '/Form':
                            self._prune_colorspaces_recursive(xo, allowed_lower, result)
        except Exception:
            # Best-effort cleanup
            pass
