import re
import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, ArrayObject, IndirectObject
from typing import List, Dict, Tuple, Optional
import io


class PDFContentParser:
    """Production-ready PDF content stream parser for removing dieline paths"""
    
    def __init__(self):
        self.debug = False
        
    def remove_cutcontour_paths(self, input_path: str, output_path: str) -> bool:
        """
        Remove CutContour and stans dieline paths from PDF by parsing and modifying content streams
        
        Args:
            input_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use pypdf for precise content stream manipulation
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            for page_num, page in enumerate(reader.pages):
                if self.debug:
                    print(f"Processing page {page_num + 1}")
                
                # Process the page to remove CutContour paths
                cleaned_page = self._clean_page_content(page)
                writer.add_page(cleaned_page)
            
            # Write the cleaned PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            return True
            
        except Exception as e:
            print(f"Error removing CutContour paths: {e}")
            return False
            
    def _clean_page_content(self, page):
        """
        Clean a page by removing CutContour-related content
        """
        # Get the content stream
        if '/Contents' in page:
            contents = page['/Contents']
            
            # Handle both single content stream and array of streams
            if isinstance(contents, list):
                # Multiple content streams
                cleaned_streams = []
                for content_stream in contents:
                    if hasattr(content_stream, 'get_object'):
                        content_stream = content_stream.get_object()
                    cleaned_content = self._clean_content_stream(content_stream)
                    if cleaned_content:
                        cleaned_streams.append(cleaned_content)
                # Update the page contents
                if cleaned_streams:
                    page[NameObject('/Contents')] = ArrayObject(cleaned_streams)
            else:
                # Single content stream
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                cleaned_content = self._clean_content_stream(contents)
                if cleaned_content:
                    page[NameObject('/Contents')] = cleaned_content
        
        # Remove CutContour color spaces from resources
        self._clean_color_spaces(page)
        
        return page
        
    def _clean_content_stream(self, content_stream):
        """
        Parse and clean a content stream to remove CutContour paths
        """
        try:
            # Get the raw content data
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
            else:
                return content_stream
                
            # Decode the content stream
            content_text = content_data.decode('latin-1')
            
            # Parse and remove CutContour-related drawing operations
            cleaned_content = self._parse_and_filter_content(content_text)
            
            # Create new content stream with cleaned data
            if hasattr(content_stream, '_data'):
                content_stream._data = cleaned_content.encode('latin-1')
            
            return content_stream
            
        except Exception as e:
            if self.debug:
                print(f"Error cleaning content stream: {e}")
            return content_stream
            
    def _parse_and_filter_content(self, content_text: str) -> str:
        """
        Parse PDF content stream and remove ONLY CutContour dieline paths (surgical removal)
        """
        lines = content_text.split('\n')
        filtered_lines = []
        
        # More conservative approach - only remove specific CutContour patterns
        # Track if we're in a CutContour drawing sequence
        in_cutcontour_path = False
        path_buffer = []
        
        # Specific CutContour patterns to identify
        cutcontour_patterns = [
            r'/CutContour\s+cs',      # Set stroke color space
            r'/CutContour\s+CS',      # Set fill color space  
            r'/CutContour\s+scn',     # Set stroke color
            r'/CutContour\s+SCN',     # Set fill color
        ]
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if this line is setting CutContour color
            is_cutcontour_color = any(re.search(pattern, line) for pattern in cutcontour_patterns)
            
            if is_cutcontour_color:
                # Start tracking a potential CutContour path
                in_cutcontour_path = True
                path_buffer = [line]  # Store the color setting line
                if self.debug:
                    print(f"Starting CutContour path tracking: {line}")
                i += 1
                continue
            
            # If we're tracking a CutContour path
            if in_cutcontour_path:
                # Add line to buffer
                path_buffer.append(line)
                
                # Check for path construction commands
                if re.match(r'^[\d\.\-\s]+m\s*$', line):  # moveto
                    pass  # Continue tracking
                elif re.match(r'^[\d\.\-\s]+l\s*$', line):  # lineto
                    pass  # Continue tracking
                elif re.match(r'^[\d\.\-\s]+c\s*$', line):  # curveto
                    pass  # Continue tracking  
                elif line == 'h':  # closepath
                    pass  # Continue tracking
                elif re.match(r'^[\d\.\-\s]+$', line):  # coordinate data
                    pass  # Continue tracking
                elif line in ['S', 's']:  # stroke operations (typical for dielines)
                    # This completes a CutContour path - remove the entire sequence
                    if self.debug:
                        print(f"Removing complete CutContour path sequence ({len(path_buffer)} lines)")
                        for buf_line in path_buffer:
                            print(f"  Removed: {buf_line}")
                    # Reset tracking without adding buffer to output
                    in_cutcontour_path = False
                    path_buffer = []
                    i += 1
                    continue
                elif line in ['B', 'b', 'f', 'f*', 'F', 'F*', 'n']:  # other drawing operations
                    # This might not be a simple dieline, be more cautious
                    # Add the buffer back to output (preserve it)
                    filtered_lines.extend(path_buffer)
                    in_cutcontour_path = False
                    path_buffer = []
                else:
                    # Unknown operation - probably not a simple dieline path
                    # Add the buffer back to output (preserve it)  
                    filtered_lines.extend(path_buffer)
                    in_cutcontour_path = False
                    path_buffer = []
                    
                i += 1
                continue
            
            # Normal line - keep it
            filtered_lines.append(line)
            i += 1
        
        # If we ended while still tracking a path, add the buffer back (preserve it)
        if in_cutcontour_path and path_buffer:
            filtered_lines.extend(path_buffer)
        
        return '\n'.join(filtered_lines)
        
    def _clean_color_spaces(self, page):
        """
        Remove CutContour color spaces from page resources
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
                    if self.debug:
                        print(f"Removing color space: {cs_name}")
            
            # Remove the identified color spaces
            for cs_name in spaces_to_remove:
                del color_spaces[cs_name]
                
        except Exception as e:
            if self.debug:
                print(f"Error cleaning color spaces: {e}")
    
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
            if hasattr(cs_def, '__getitem__') and len(cs_def) > 1:
                if str(cs_def[0]) == '/Separation':
                    color_name = str(cs_def[1]).replace('/', '')
                    if color_name in ['CutContour', 'cutcontour', 'CUTCONTOUR']:
                        return True
        except:
            pass
            
        return False
        
    def verify_removal(self, pdf_path: str) -> Dict:
        """
        Verify that CutContour elements have been removed
        """
        try:
            reader = PdfReader(pdf_path)
            
            verification = {
                'cutcontour_colorspaces': 0,
                'cutcontour_references': 0,
                'pages_checked': len(reader.pages)
            }
            
            for page in reader.pages:
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
        Check if content stream has CutContour references
        """
        try:
            if hasattr(content_stream, 'get_data'):
                content_data = content_stream.get_data()
                content_text = content_data.decode('latin-1')
                return 'CutContour' in content_text
        except:
            pass
        return False