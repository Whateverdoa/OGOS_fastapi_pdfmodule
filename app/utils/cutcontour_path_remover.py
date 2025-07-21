import re
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, ArrayObject
from typing import Dict, List
import io


class CutContourPathRemover:
    """
    Surgically removes only CutContour dieline paths while preserving all design content
    """
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_dieline(self, input_path: str, output_path: str) -> Dict:
        """
        Remove only the CutContour dieline paths, preserving all other design elements
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            Dict with processing results
        """
        result = {
            'success': False,
            'cutcontour_paths_removed': 0,
            'design_paths_preserved': 0,
            'colorspaces_removed': 0,
            'error': None
        }
        
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Process the page to remove only CutContour dieline
                processed_page = self._process_page(page, result)
                writer.add_page(processed_page)
            
            # Write the processed PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            result['success'] = True
            return result
            
        except Exception as e:
            result['error'] = str(e)
            if self.debug:
                print(f"Error processing PDF: {e}")
            return result
    
    def _process_page(self, page, result: Dict):
        """
        Process a single page to remove CutContour dieline
        """
        # Remove CutContour color spaces
        self._remove_cutcontour_colorspaces(page, result)
        
        # Remove only CutContour paths from content streams
        self._filter_content_streams(page, result)
        
        return page
    
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
                if self._is_cutcontour_colorspace(cs_name, cs_def):
                    spaces_to_remove.append(cs_name)
                    result['colorspaces_removed'] += 1
                    if self.debug:
                        print(f"Removing color space: {cs_name}")
            
            # Remove the color spaces
            for cs_name in spaces_to_remove:
                del color_spaces[cs_name]
                
        except Exception as e:
            if self.debug:
                print(f"Error removing color spaces: {e}")
    
    def _filter_content_streams(self, page, result: Dict):
        """
        Filter content streams to remove only CutContour paths
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            
            if isinstance(contents, list):
                # Multiple content streams
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    self._filter_single_stream(content_stream, result)
            else:
                # Single content stream
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                self._filter_single_stream(contents, result)
                
        except Exception as e:
            if self.debug:
                print(f"Error filtering content streams: {e}")
    
    def _filter_single_stream(self, content_stream, result: Dict):
        """
        Filter a single content stream to remove CutContour paths
        """
        try:
            if not hasattr(content_stream, 'get_data'):
                return
                
            # Get the content
            content_data = content_stream.get_data()
            content_text = content_data.decode('latin-1')
            
            # Filter the content
            filtered_text = self._remove_cutcontour_sequences(content_text, result)
            
            # Update the stream if content changed
            if filtered_text != content_text:
                # Update the content stream data properly
                try:
                    new_data = filtered_text.encode('latin-1')
                    
                    # Force decode first, then update
                    content_stream.update({})  # This forces decode
                    content_stream._data = new_data
                    
                    if self.debug:
                        print(f"Updated content stream with {len(new_data)} bytes")
                        
                except Exception as e:
                    if self.debug:
                        print(f"Error updating stream data: {e}")
                    # Fallback - try different approach
                    pass
                    
        except Exception as e:
            if self.debug:
                print(f"Error filtering stream: {e}")
    
    def _remove_cutcontour_sequences(self, content_text: str, result: Dict) -> str:
        """
        Remove sequences that use CutContour color while preserving other paths
        """
        lines = content_text.split('\n')
        filtered_lines = []
        
        skip_until_end = False
        cutcontour_sequence = []
        paths_removed = 0
        paths_kept = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check if this line sets CutContour color
            if re.search(r'/CutContour\s+(cs|CS|scn|SCN)', line):
                # Start of a CutContour sequence
                skip_until_end = True
                cutcontour_sequence = [line]
                if self.debug:
                    print(f"Found CutContour color setting: {line}")
                continue
            
            if skip_until_end:
                cutcontour_sequence.append(line)
                
                # Check for path drawing operators that end the sequence
                if line in ['S', 's', 'f', 'F', 'f*', 'F*', 'B', 'b', 'B*', 'b*', 'n']:
                    # End of path - this was a CutContour path, remove it
                    paths_removed += 1
                    result['cutcontour_paths_removed'] += 1
                    if self.debug:
                        print(f"Removed CutContour path sequence ({len(cutcontour_sequence)} lines)")
                        if len(cutcontour_sequence) <= 5:
                            for seq_line in cutcontour_sequence:
                                print(f"  Removed: {seq_line}")
                    
                    # Reset and continue without adding to output
                    skip_until_end = False
                    cutcontour_sequence = []
                    continue
                elif re.match(r'^[0-9.\-\s]+[mlcvyh]?\s*$', line) or line == 'h':
                    # Path construction commands, continue collecting
                    continue
                else:
                    # Unknown command while in CutContour sequence
                    # Be conservative and keep it
                    filtered_lines.extend(cutcontour_sequence)
                    skip_until_end = False
                    cutcontour_sequence = []
                    paths_kept += 1
            else:
                # Normal line - keep it
                filtered_lines.append(line)
                # Count other drawing operations as preserved paths
                if line in ['S', 's', 'f', 'F', 'f*', 'F*', 'B', 'b', 'B*', 'b*', 'n']:
                    paths_kept += 1
        
        # If we ended in the middle of a sequence, preserve it
        if skip_until_end and cutcontour_sequence:
            filtered_lines.extend(cutcontour_sequence)
            paths_kept += 1
        
        result['design_paths_preserved'] += paths_kept
        
        if self.debug:
            print(f"Stream processing: {paths_removed} CutContour paths removed, {paths_kept} design paths kept")
        
        return '\n'.join(filtered_lines)
    
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
            # Handle IndirectObject references
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()
                
            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__') and len(cs_def) > 1:
                if str(cs_def[0]) == '/Separation':
                    color_name = str(cs_def[1]).replace('/', '')
                    if color_name.lower() in ['cutcontour', 'cut_contour']:
                        return True
        except:
            pass
            
        return False
    
    def verify_removal(self, pdf_path: str) -> Dict:
        """
        Verify the removal results
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'pages_processed': len(reader.pages),
                'cutcontour_colorspaces_found': 0,
                'cutcontour_references_found': 0,
                'has_content': False
            }
            
            for page in reader.pages:
                # Check if page has content
                if '/Contents' in page:
                    verification['has_content'] = True
                
                # Check for remaining CutContour color spaces
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    color_spaces = page['/Resources']['/ColorSpace']
                    for cs_name, cs_def in color_spaces.items():
                        if self._is_cutcontour_colorspace(cs_name, cs_def):
                            verification['cutcontour_colorspaces_found'] += 1
                
                # Check for CutContour references in content
                if '/Contents' in page:
                    contents = page['/Contents']
                    if isinstance(contents, list):
                        for content_stream in contents:
                            if hasattr(content_stream, 'get_object'):
                                content_stream = content_stream.get_object()
                            if self._stream_has_cutcontour(content_stream):
                                verification['cutcontour_references_found'] += 1
                    else:
                        if hasattr(contents, 'get_object'):
                            contents = contents.get_object()
                        if self._stream_has_cutcontour(contents):
                            verification['cutcontour_references_found'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}
    
    def _stream_has_cutcontour(self, content_stream) -> bool:
        """
        Check if stream contains CutContour references
        """
        try:
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
                content_text = content_data.decode('latin-1', errors='ignore')
                return 'CutContour' in content_text
        except:
            pass
        return False