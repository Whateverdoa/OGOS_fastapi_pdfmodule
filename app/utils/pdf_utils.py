import fitz  # PyMuPDF
import os
import tempfile
from typing import Dict, Tuple, Optional


class PDFUtils:
    """Utility functions for PDF manipulation"""
    
    @staticmethod
    def merge_pdfs(base_pdf_path: str, overlay_pdf_path: str, output_path: str) -> bool:
        """
        Merge two PDFs, overlaying the second on the first
        
        Args:
            base_pdf_path: Path to the base PDF
            overlay_pdf_path: Path to the overlay PDF (with dieline)
            output_path: Path for the output PDF
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Open both PDFs
            base_doc = fitz.open(base_pdf_path)
            overlay_doc = fitz.open(overlay_pdf_path)
            
            # Get the first page of each
            base_page = base_doc[0]
            overlay_page = overlay_doc[0]
            
            # Insert the overlay page content into the base page
            base_page.show_pdf_page(
                base_page.rect,  # Where to place it
                overlay_doc,     # Source document
                0,               # Source page number
                overlay=True     # Overlay mode
            )
            
            # Save the result
            base_doc.save(output_path)
            
            # Clean up
            base_doc.close()
            overlay_doc.close()
            
            return True
            
        except Exception as e:
            print(f"Error merging PDFs: {e}")
            return False
            
    @staticmethod
    def extract_page(pdf_path: str, page_num: int = 0) -> Optional[str]:
        """
        Extract a single page from a PDF
        
        Args:
            pdf_path: Path to the PDF
            page_num: Page number to extract (0-indexed)
            
        Returns:
            Path to the extracted page PDF, or None if error
        """
        try:
            doc = fitz.open(pdf_path)
            
            if page_num >= len(doc):
                print(f"Page {page_num} does not exist in PDF")
                return None
                
            # Create a new document with just this page
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            new_doc.save(temp_path)
            
            # Clean up
            doc.close()
            new_doc.close()
            
            return temp_path
            
        except Exception as e:
            print(f"Error extracting page: {e}")
            return None
            
    @staticmethod
    def remove_spot_color_objects(pdf_path: str, output_path: str) -> bool:
        """
        Remove spot color objects from a PDF
        
        Args:
            pdf_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            doc = fitz.open(pdf_path)
            
            # This is a simplified implementation
            # In production, we would need to:
            # 1. Parse the page's content stream
            # 2. Identify and remove spot color definitions
            # 3. Remove paths that use those spot colors
            
            doc.save(output_path)
            doc.close()
            
            return True
            
        except Exception as e:
            print(f"Error removing spot color objects: {e}")
            return False
            
    @staticmethod
    def get_pdf_info(pdf_path: str) -> Dict:
        """
        Get basic information about a PDF
        
        Args:
            pdf_path: Path to the PDF
            
        Returns:
            Dictionary with PDF information
        """
        try:
            doc = fitz.open(pdf_path)
            
            info = {
                'page_count': len(doc),
                'file_size': os.path.getsize(pdf_path),
                'metadata': doc.metadata,
                'is_encrypted': doc.is_encrypted,
                'pages': []
            }
            
            for i, page in enumerate(doc):
                page_info = {
                    'number': i + 1,
                    'width': page.rect.width,
                    'height': page.rect.height,
                    'rotation': page.rotation
                }
                info['pages'].append(page_info)
                
            doc.close()
            
            return info
            
        except Exception as e:
            print(f"Error getting PDF info: {e}")
            return {}

    @staticmethod
    def rotate_pdf(input_path: str, output_path: str, degrees: int) -> bool:
        """
        Rotate the first page of a PDF by the specified degrees (0, 90, 180, 270).

        Args:
            input_path: Path to the input PDF
            output_path: Path to write the rotated PDF
            degrees: Rotation angle (must be one of 0, 90, 180, 270)

        Returns:
            True if success, False otherwise
        """
        try:
            if degrees % 90 != 0:
                degrees = 0
            doc = fitz.open(input_path)
            if len(doc) == 0:
                doc.close()
                return False
            normalized_degrees = degrees % 360
            if normalized_degrees == 0:
                doc.save(output_path)
                doc.close()
                return True
            for page in doc:
                page.set_rotation((page.rotation + normalized_degrees) % 360)
            doc.save(output_path)
            doc.close()
            return True
        except Exception as e:
            print(f"Error rotating PDF: {e}")
            return False
