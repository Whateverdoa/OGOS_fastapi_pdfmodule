from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, ArrayObject
from typing import Dict, Optional
import re


class SpotColorRenamer:
    """Simple spot color renamer that preserves all content"""
    
    def __init__(self):
        self.debug = False
        
    def rename_cutcontour_to_stans(self, input_path: str, output_path: str, new_color_name: str = "stans") -> bool:
        """
        Rename CutContour spot color to stans while preserving all content
        
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
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Rename spot colors in resources
                self._rename_colorspaces_in_page(page, new_color_name)
                
                # Rename spot color references in content streams
                self._rename_content_references(page, new_color_name)
                
                writer.add_page(page)
            
            # Write the renamed PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            return True
            
        except Exception as e:
            print(f"Error renaming spot color: {e}")
            return False
            
    def _rename_colorspaces_in_page(self, page, new_color_name: str):
        """
        Rename CutContour color spaces in page resources
        """
        try:
            if '/Resources' not in page:
                return
                
            resources = page['/Resources']
            if '/ColorSpace' not in resources:
                return
                
            color_spaces = resources['/ColorSpace']
            
            # Find CutContour color spaces and rename them
            spaces_to_rename = {}
            for cs_name, cs_def in color_spaces.items():
                if self._is_cutcontour_colorspace(cs_name, cs_def):
                    # Create new color space definition with renamed color
                    new_cs_def = self._create_renamed_colorspace(cs_def, new_color_name)
                    spaces_to_rename[cs_name] = new_cs_def
                    if self.debug:
                        print(f"Found CutContour color space: {cs_name} -> renaming to {new_color_name}")
            
            # Apply the renames
            for cs_name, new_cs_def in spaces_to_rename.items():
                color_spaces[cs_name] = new_cs_def
                
        except Exception as e:
            if self.debug:
                print(f"Error renaming color spaces: {e}")
    
    def _rename_content_references(self, page, new_color_name: str):
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
                    self._rename_in_content_stream(content_stream, new_color_name)
            else:
                # Single content stream
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                self._rename_in_content_stream(contents, new_color_name)
                
        except Exception as e:
            if self.debug:
                print(f"Error renaming content references: {e}")
                
    def _rename_in_content_stream(self, content_stream, new_color_name: str):
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
            updated_content = content_text.replace('/CutContour', f'/{new_color_name}')
            
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
    
    def _is_cutcontour_colorspace(self, cs_name: str, cs_def) -> bool:
        """
        Check if a color space is CutContour
        """
        # Check name
        if 'CutContour' in str(cs_name):
            return True
            
        # Check definition
        def_str = str(cs_def)
        if 'CutContour' in def_str:
            return True
            
        # Check for Separation color space with CutContour
        try:
            if hasattr(cs_def, '__getitem__') and len(cs_def) > 1:
                if str(cs_def[0]) == '/Separation':
                    color_name = str(cs_def[1]).replace('/', '')
                    if color_name in ['CutContour', 'cutcontour', 'CUTCONTOUR']:
                        return True
        except:
            pass
            
        return False
    
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