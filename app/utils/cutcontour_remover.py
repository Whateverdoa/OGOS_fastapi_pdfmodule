import re
import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, ArrayObject, IndirectObject
from typing import List, Dict, Tuple, Optional
import io


class CutContourRemover:
    """Specifically targets and removes CutContour vector lines and paths"""
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_vectors(self, input_path: str, output_path: str) -> Dict:
        """
        Completely remove all CutContour vector lines and paths from PDF
        
        This function specifically targets:
        - CutContour spot color definitions
        - All vector paths using CutContour color
        - CutContour color space references
        - Leaves all other design elements intact
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            Dict with removal statistics
        """
        stats = {
            'cutcontour_colorspaces_removed': 0,
            'cutcontour_paths_removed': 0,
            'total_paths_before': 0,
            'total_paths_after': 0,
            'success': False
        }
        
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Count total paths before processing
                paths_before = self._count_paths_in_page(page)
                stats['total_paths_before'] += paths_before
                
                # Remove CutContour elements from the page
                cleaned_page = self._remove_cutcontour_from_page(page, stats)
                
                # Count paths after processing
                paths_after = self._count_paths_in_page(cleaned_page)
                stats['total_paths_after'] += paths_after
                
                writer.add_page(cleaned_page)
            
            # Write the cleaned PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            stats['success'] = True
            return stats
            
        except Exception as e:
            stats['error'] = str(e)
            if self.debug:
                print(f"Error removing CutContour vectors: {e}")
            return stats
    
    def _remove_cutcontour_from_page(self, page, stats: Dict):
        """
        Remove all CutContour elements from a page
        """
        # Remove CutContour color spaces first
        self._remove_cutcontour_colorspaces(page, stats)
        
        # Remove CutContour vector paths from content streams
        self._remove_cutcontour_paths(page, stats)
        
        return page
    
    def _remove_cutcontour_colorspaces(self, page, stats: Dict):
        """
        Remove CutContour color space definitions
        """
        try:
            if '/Resources' not in page:
                return
                
            resources = page['/Resources']
            if '/ColorSpace' not in resources:
                return
                
            color_spaces = resources['/ColorSpace']
            
            # Find and remove CutContour color spaces
            spaces_to_remove = []
            for cs_name, cs_def in color_spaces.items():
                if self._is_cutcontour_colorspace(cs_name, cs_def):
                    spaces_to_remove.append(cs_name)
                    stats['cutcontour_colorspaces_removed'] += 1
                    if self.debug:
                        print(f"Removing color space: {cs_name}")
            
            # Remove the identified color spaces
            for cs_name in spaces_to_remove:
                del color_spaces[cs_name]
                
        except Exception as e:
            if self.debug:
                print(f"Error removing color spaces: {e}")
    
    def _remove_cutcontour_paths(self, page, stats: Dict):
        """
        Remove vector paths that use CutContour color
        """
        try:
            if '/Contents' not in page:
                return
                
            contents = page['/Contents']
            
            # Handle both single content stream and array of streams
            if isinstance(contents, list):
                # Multiple content streams
                cleaned_streams = []
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    cleaned_content = self._remove_cutcontour_from_stream(content_stream, stats)
                    if cleaned_content is not None:
                        cleaned_streams.append(cleaned_content)
                
                # Update the page contents
                if cleaned_streams:
                    page[NameObject('/Contents')] = ArrayObject(cleaned_streams)
                else:
                    # Remove empty contents
                    if NameObject('/Contents') in page:
                        del page[NameObject('/Contents')]
            else:
                # Single content stream
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                cleaned_content = self._remove_cutcontour_from_stream(contents, stats)
                if cleaned_content is not None:
                    page[NameObject('/Contents')] = cleaned_content
                else:
                    # Remove empty contents
                    if NameObject('/Contents') in page:
                        del page[NameObject('/Contents')]
                
        except Exception as e:
            if self.debug:
                print(f"Error removing CutContour paths: {e}")
    
    def _remove_cutcontour_from_stream(self, content_stream, stats: Dict):
        """
        Remove CutContour vector paths from a content stream
        """
        try:
            # Get the raw content data
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
            else:
                return content_stream
                
            # Decode the content stream
            content_text = content_data.decode('latin-1')
            
            # Parse and remove CutContour paths
            filtered_content = self._filter_cutcontour_paths(content_text, stats)
            
            if filtered_content != content_text:
                # Update content stream with filtered data
                content_stream.update({})  # Force decode
                content_stream._data = filtered_content.encode('latin-1')
                
                # Force re-encoding for proper storage
                if hasattr(content_stream, 'flate_encode'):
                    content_stream.flate_encode()
            
            return content_stream
            
        except Exception as e:
            if self.debug:
                print(f"Error filtering content stream: {e}")
            return content_stream
    
    def _filter_cutcontour_paths(self, content_text: str, stats: Dict) -> str:
        """
        Filter out complete CutContour vector paths from content stream
        """
        lines = content_text.split('\\n')
        filtered_lines = []
        
        # Track CutContour path sequences
        in_cutcontour_sequence = False
        sequence_buffer = []
        paths_removed = 0
        
        # CutContour color setting patterns
        cutcontour_patterns = [
            r'/CutContour\\s+cs',      # Set stroke color space
            r'/CutContour\\s+CS',      # Set fill color space  
            r'/CutContour\\s+scn',     # Set stroke color
            r'/CutContour\\s+SCN',     # Set fill color
            r'\\b\\w*CutContour\\w*\\b', # Any CutContour reference
        ]
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if this line references CutContour
            is_cutcontour_line = any(re.search(pattern, line) for pattern in cutcontour_patterns)
            
            if is_cutcontour_line:
                # Start tracking a CutContour sequence
                in_cutcontour_sequence = True
                sequence_buffer = [line]
                if self.debug:
                    print(f"Starting CutContour sequence: {line}")
                i += 1
                continue
            
            # If we're in a CutContour sequence, collect the path
            if in_cutcontour_sequence:
                sequence_buffer.append(line)
                
                # Check for path construction and drawing commands
                if (re.match(r'^[\\d\\.\\-\\s]+[ml]\\s*$', line) or  # moveto/lineto
                    re.match(r'^[\\d\\.\\-\\s]+c\\s*$', line) or      # curveto
                    re.match(r'^[\\d\\.\\-\\s]+[vxy]\\s*$', line) or  # curve variations
                    line == 'h' or                                     # closepath
                    re.match(r'^[\\d\\.\\-\\s]*$', line)):             # coordinate data
                    # Continue collecting path data
                    pass
                elif line in ['S', 's', 'f', 'f*', 'F', 'F*', 'B', 'b', 'b*', 'n']:
                    # Path drawing operation - complete CutContour path
                    paths_removed += 1
                    stats['cutcontour_paths_removed'] += 1
                    if self.debug:
                        print(f"Removed complete CutContour path ({len(sequence_buffer)} lines)")
                        if self.debug and len(sequence_buffer) <= 10:
                            for buf_line in sequence_buffer:
                                print(f"  Removed: {buf_line}")
                    
                    # Reset sequence tracking without adding to output
                    in_cutcontour_sequence = False
                    sequence_buffer = []
                    i += 1
                    continue
                else:
                    # Unknown operation - might not be a vector path
                    # Be conservative and preserve it
                    filtered_lines.extend(sequence_buffer)
                    in_cutcontour_sequence = False
                    sequence_buffer = []
            else:
                # Normal line - keep it
                filtered_lines.append(line)
            
            i += 1
        
        # If we ended while still in a sequence, preserve it (conservative)
        if in_cutcontour_sequence and sequence_buffer:
            filtered_lines.extend(sequence_buffer)
        
        if self.debug and paths_removed > 0:
            print(f"Total CutContour paths removed from this stream: {paths_removed}")
        
        return '\\n'.join(filtered_lines)
    
    def _is_cutcontour_colorspace(self, cs_name: str, cs_def) -> bool:
        """
        Check if a color space is related to CutContour
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
                    if color_name in ['CutContour', 'cutcontour', 'CUTCONTOUR']:
                        return True
        except:
            pass
            
        return False
    
    def _count_paths_in_page(self, page) -> int:
        """
        Count total drawing paths in a page (for statistics)
        """
        try:
            path_count = 0
            
            if '/Contents' not in page:
                return 0
                
            contents = page['/Contents']
            
            if isinstance(contents, list):
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    path_count += self._count_paths_in_stream(content_stream)
            else:
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                path_count = self._count_paths_in_stream(contents)
            
            return path_count
            
        except:
            return 0
    
    def _count_paths_in_stream(self, content_stream) -> int:
        """
        Count drawing paths in a content stream
        """
        try:
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
                content_text = content_data.decode('latin-1', errors='ignore')
                
                # Count path drawing operators
                drawing_ops = ['S', 's', 'f', 'f*', 'F', 'F*', 'B', 'b', 'b*']
                path_count = sum(content_text.count(f' {op} ') + content_text.count(f'\\n{op}\\n') + 
                               content_text.count(f'\\n{op} ') for op in drawing_ops)
                return path_count
        except:
            pass
        return 0
    
    def verify_removal(self, pdf_path: str) -> Dict:
        """
        Verify that CutContour elements have been completely removed
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'cutcontour_colorspaces': 0,
                'cutcontour_references': 0,
                'total_paths': 0,
                'pages_checked': len(reader.pages)
            }
            
            for page in reader.pages:
                # Count total paths
                verification['total_paths'] += self._count_paths_in_page(page)
                
                # Check color spaces
                if '/Resources' in page and '/ColorSpace' in page['/Resources']:
                    color_spaces = page['/Resources']['/ColorSpace']
                    for cs_name, cs_def in color_spaces.items():
                        if self._is_cutcontour_colorspace(cs_name, cs_def):
                            verification['cutcontour_colorspaces'] += 1
                
                # Check content streams for CutContour references
                if '/Contents' in page:
                    contents = page['/Contents']
                    if isinstance(contents, list):
                        for content_stream in contents:
                            if hasattr(content_stream, 'get_object'):
                                content_stream = content_stream.get_object()
                            if self._has_cutcontour_references(content_stream):
                                verification['cutcontour_references'] += 1
                    else:
                        if hasattr(contents, 'get_object'):
                            contents = contents.get_object()
                        if self._has_cutcontour_references(contents):
                            verification['cutcontour_references'] += 1
            
            return verification
            
        except Exception as e:
            return {'error': str(e)}
    
    def _has_cutcontour_references(self, content_stream) -> bool:
        """
        Check if content stream has any CutContour references
        """
        try:
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
                content_text = content_data.decode('latin-1', errors='ignore')
                return 'CutContour' in content_text
        except:
            pass
        return False