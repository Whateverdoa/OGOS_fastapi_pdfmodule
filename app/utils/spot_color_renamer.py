from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, ArrayObject, TextStringObject
from typing import Dict, Optional, Set
import re


class SpotColorRenamer:
    """Simple spot color renamer that preserves all content"""
    TARGET_SPOT_NAMES = {
        'cutcontour', 'cut contour', 'cut_contour',
        'kisscut', 'kiss cut', 'kiss_cut',
        'stans', 'stanslijn',
        'diecut', 'die cut', 'die_cut',
    }
    
    def __init__(self):
        self.debug = False
        
    def rename_cutcontour_to_stans(self, input_path: str, output_path: str, new_color_name: str = "stans") -> bool:
        """
        Rename common dieline spot colors (CutContour/KissCut/etc.) to the provided name while preserving content
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path  
            new_color_name: New spot color name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            renamed_tokens: Set[str] = set()

            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Rename spot colors in resources
                page_tokens = self._rename_resources(page.get('/Resources'), new_color_name)
                renamed_tokens.update(page_tokens)
                self._rename_optional_content_groups_in_dict(page.get('/Resources'), new_color_name)
                
                # Rename spot color references in content streams
                self._rename_content_references(page, new_color_name, renamed_tokens)
                
                writer.add_page(page)

            self._rename_document_ocproperties(reader, new_color_name)
            
            # Write the renamed PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            return True
            
        except Exception as e:
            print(f"Error renaming spot color: {e}")
            return False
            
    def _rename_resources(self, resources, new_color_name: str) -> Set[str]:
        renamed_tokens: Set[str] = set()
        if not resources:
            return renamed_tokens

        try:
            resources_obj = resources.get_object() if hasattr(resources, 'get_object') else resources

            color_spaces = resources_obj.get('/ColorSpace')
            if color_spaces:
                spaces_to_rename = {}
                for cs_name, cs_def in color_spaces.items():
                    source_name = self._detect_target_color_name(cs_def)
                    if source_name:
                        new_cs_def = self._create_renamed_colorspace(cs_def, new_color_name)
                        spaces_to_rename[cs_name] = new_cs_def
                        renamed_tokens.add(source_name)
                        if self.debug:
                            print(f"Renaming spot color {source_name} in {cs_name} to {new_color_name}")
                for cs_name, new_cs_def in spaces_to_rename.items():
                    color_spaces[cs_name] = new_cs_def

            # Recurse into XObjects
            xobjects = resources_obj.get('/XObject')
            if xobjects:
                for xobj_name, xobj in xobjects.items():
                    target = xobj.get_object() if hasattr(xobj, 'get_object') else xobj
                    if isinstance(target, DictionaryObject):
                        renamed_tokens.update(
                            self._rename_resources(target.get('/Resources'), new_color_name)
                        )
                        self._rename_optional_content_groups_in_dict(target.get('/Resources'), new_color_name)

        except Exception as exc:
            if self.debug:
                print(f"Error renaming resources: {exc}")

        return renamed_tokens

    def _rename_optional_content_groups_in_dict(self, resources, new_color_name: str):
        try:
            res_obj = resources.get_object() if hasattr(resources, 'get_object') else resources
            if not res_obj:
                return
            properties = res_obj.get('/Properties')
            if not properties:
                return
            for name, prop in properties.items():
                ocg = prop.get_object() if hasattr(prop, 'get_object') else prop
                self._rename_ocg_dictionary(ocg, new_color_name)
        except Exception as exc:
            if self.debug:
                print(f"Error renaming OCGs in dict: {exc}")

    def _detect_target_color_name(self, cs_def) -> Optional[str]:
        try:
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()

            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__'):
                if len(cs_def) > 1 and str(cs_def[0]) == '/Separation':
                    color_token = str(cs_def[1])
                    color_name = color_token.lstrip('/')
                    if color_name.lower() in self.TARGET_SPOT_NAMES:
                        return color_token

            cs_text = str(cs_def).lower()
            for alias in self.TARGET_SPOT_NAMES:
                if alias in cs_text:
                    return alias
        except Exception as exc:
            if self.debug:
                print(f"Error detecting color name: {exc}")
        return None

    def _rename_document_ocproperties(self, reader: PdfReader, new_color_name: str):
        try:
            catalog = reader.trailer.get('/Root')
            if not catalog or '/OCProperties' not in catalog:
                return
            ocprops = catalog['/OCProperties']
            visited: Set[int] = set()
            self._rename_in_structure(ocprops, new_color_name, visited)
        except Exception as exc:
            if self.debug:
                print(f"Error renaming document OCGs: {exc}")

    def _rename_in_structure(self, obj, new_color_name: str, visited: Set[int]):
        if obj is None:
            return

        target = obj.get_object() if hasattr(obj, 'get_object') else obj
        key = id(target)
        if key in visited:
            return
        visited.add(key)

        if isinstance(target, DictionaryObject):
            if target.get('/Type') == '/OCG':
                self._rename_ocg_dictionary(target, new_color_name)
            for value in list(target.values()):
                self._rename_in_structure(value, new_color_name, visited)
        elif isinstance(target, ArrayObject):
            for value in target:
                self._rename_in_structure(value, new_color_name, visited)

    def _rename_ocg_dictionary(self, ocg_dict, new_color_name: str):
        if not isinstance(ocg_dict, DictionaryObject):
            return
        name_value = ocg_dict.get('/Name')
        if isinstance(name_value, str):
            if name_value.lower() in self.TARGET_SPOT_NAMES:
                ocg_dict[NameObject('/Name')] = TextStringObject(new_color_name)
                if self.debug:
                    print(f"Renamed OCG name from {name_value} to {new_color_name}")
    def _rename_content_references(self, page, new_color_name: str, spot_tokens: Set[str]):
        """
        Rename CutContour references in content streams
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            
            # Handle both single content stream and array of streams
            if isinstance(contents, list):
                # Multiple content streams
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    self._rename_in_content_stream(content_stream, new_color_name, spot_tokens)
            else:
                # Single content stream
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                self._rename_in_content_stream(contents, new_color_name, spot_tokens)
                
        except Exception as e:
            if self.debug:
                print(f"Error renaming content references: {e}")
                
    def _rename_in_content_stream(self, content_stream, new_color_name: str, spot_tokens: Set[str]):
        """
        Rename CutContour references in a single content stream
        """
        try:
            # Get the raw content data
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
            else:
                return
                
            # Decode the content stream
            content_text = content_data.decode('latin-1')
            
            if self.debug and 'CutContour' in content_text:
                print(f"Found CutContour in content stream")
            
            # Replace CutContour references with new color name
            # This preserves all paths and just changes the color reference
            updated_content = content_text
            replacements = self._build_replacement_tokens(spot_tokens, new_color_name)
            for old_token in replacements:
                updated_content = updated_content.replace(old_token, f'/{new_color_name}')
            
            if updated_content != content_text:
                if self.debug:
                    print(f"Renamed CutContour references in content stream to {new_color_name}")
                
                # Update content using the filter stack
                content_stream.update({})  # Force decode
                content_stream._data = updated_content.encode('latin-1')
                
                # Force re-encoding for proper storage
                if hasattr(content_stream, 'flate_encode'):
                    content_stream.flate_encode()
                    
        except Exception as e:
            if self.debug:
                print(f"Error renaming content stream: {e}")
    
    def _build_replacement_tokens(self, spot_tokens: Set[str], new_color_name: str) -> Set[str]:
        tokens: Set[str] = set()
        for token in spot_tokens:
            if not token:
                continue
            base = token.lstrip('/')
            variations = {
                token,
                f'/{base}',
                f'/{base.lower()}',
                f'/{base.upper()}',
                f'/{base.title()}',
            }
            tokens.update(variations)

        # Also support generic aliases even if color spaces weren't found
        for alias in self.TARGET_SPOT_NAMES:
            tokens.add(f'/{alias}')
            tokens.add(f'/{alias.replace(" ", "")}')
            tokens.add(f'/{alias.replace("_", "")}')

        tokens.discard(f'/{new_color_name}')
        tokens.discard(f'/{new_color_name.lower()}')
        tokens.discard(f'/{new_color_name.upper()}')

        return tokens
    
    def _create_renamed_colorspace(self, cs_def, new_color_name: str):
        """
        Create a new color space definition with renamed color
        """
        try:
            # Handle IndirectObject references
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()
                
            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__') and len(cs_def) > 1:
                if str(cs_def[0]) == '/Separation':
                    # Create new separation color space with new name by modifying existing
                    if hasattr(cs_def, '__setitem__'):
                        cs_def[1] = NameObject(f'/{new_color_name}')
                        if self.debug:
                            print(f"Updated Separation color space name to {new_color_name}")
                        return cs_def
                    else:
                        # Create new separation color space with new name
                        new_cs_def = ArrayObject()
                        new_cs_def.append(NameObject('/Separation'))
                        new_cs_def.append(NameObject(f'/{new_color_name}'))
                        
                        # Copy the rest of the definition (alternate color space, tint transform)
                        for i in range(2, len(cs_def)):
                            new_cs_def.append(cs_def[i])
                        
                        if self.debug:
                            print(f"Created new Separation color space with name {new_color_name}")
                        return new_cs_def
        except Exception as e:
            if self.debug:
                print(f"Error creating renamed colorspace: {e}")
            pass
            
        # Fallback: return original if can't parse
        return cs_def
    
    def verify_rename(self, pdf_path: str) -> Dict:
        """
        Verify that spot color renaming worked
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'cutcontour_found': 0,
                'stans_found': 0,
                'pages_checked': len(reader.pages)
            }
            
            for page in reader.pages:
                # Check color spaces
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    color_spaces = page['/Resources']['/ColorSpace']
                    for cs_name, cs_def in color_spaces.items():
                        def_str = str(cs_def)
                        if 'CutContour' in def_str:
                            verification['cutcontour_found'] += 1
                        if 'stans' in def_str:
                            verification['stans_found'] += 1
                
                # Check content streams
                if '/Contents' in page:
                    contents = page['/Contents']
                    if isinstance(contents, list):
                        for content_stream in contents:
                            if hasattr(content_stream, 'get_object'):
                                content_stream = content_stream.get_object()
                            if hasattr(content_stream, 'get_data'):
                                content_text = content_stream.get_data().decode('latin-1', errors='ignore')
                                if 'CutContour' in content_text:
                                    verification['cutcontour_found'] += 1
                                if 'stans' in content_text:
                                    verification['stans_found'] += 1
                    else:
                        if hasattr(contents, 'get_object'):
                            contents = contents.get_object()
                        if hasattr(contents, 'get_data'):
                            content_text = contents.get_data().decode('latin-1', errors='ignore')
                            if 'CutContour' in content_text:
                                verification['cutcontour_found'] += 1
                            if 'stans' in content_text:
                                verification['stans_found'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}
