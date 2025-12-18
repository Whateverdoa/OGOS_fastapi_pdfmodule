import fitz  # PyMuPDF
try:
    from pypdf import PdfReader, PdfWriter, PdfMerger
except ImportError:
    # Newer versions of pypdf use different import
    from pypdf import PdfReader, PdfWriter
    try:
        from pypdf import PdfWriter as PdfMerger  # Fallback
    except ImportError:
        PdfMerger = PdfWriter
import os
import tempfile
from typing import Dict, Tuple, Optional
from pypdf.generic import NameObject, DictionaryObject, NumberObject, BooleanObject
import subprocess, shutil


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
    def ensure_overprint_for_spot(pdf_path: str, spot_name: str = "stans") -> bool:
        """
        Ensure that drawing operations using a given spot (e.g., stans)
        in Form XObjects run with overprint enabled (OP/op true).

        Implementation: scans page XObjects; for each Form whose content or
        resources mention the spot name, injects an ExtGState with /OP true,
        /op true, and prepends '/GSop gs' at the start of the form stream.
        """
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            patched = False

            for page in reader.pages:
                resources = page.get('/Resources')
                if hasattr(resources, 'get_object'):
                    resources = resources.get_object()
                if not resources or '/XObject' not in resources:
                    writer.add_page(page)
                    continue

                xobjs = resources['/XObject']
                if hasattr(xobjs, 'get_object'):
                    xobjs = xobjs.get_object()

                # iterate XObjects
                for name, xo in list(xobjs.items()):
                    if hasattr(xo, 'get_object'):
                        xo = xo.get_object()
                    subtype = str(xo.get('/Subtype')) if hasattr(xo, 'get') else ''
                    if subtype != '/Form':
                        continue

                    # Prefer patching PyMuPDF overlay forms (named like fzFrmN)
                    name_str = str(name)
                    content_uses_spot = name_str.startswith('/fzFrm')
                    if hasattr(xo, 'get_data'):
                        try:
                            data = xo.get_data().decode('latin-1', errors='ignore')
                        except Exception:
                            data = ''
                        if (spot_name in data or spot_name.lower() in data.lower()):
                            content_uses_spot = True

                    xr = xo.get('/Resources') if hasattr(xo, 'get') else None
                    if hasattr(xr, 'get_object'):
                        xr = xr.get_object()
                    if xr and '/ColorSpace' in xr:
                        cs = xr['/ColorSpace']
                        if hasattr(cs, 'get_object'):
                            cs = cs.get_object()
                        for _, cs_def in getattr(cs, 'items', lambda: [])():
                            if spot_name in str(cs_def) or spot_name.lower() in str(cs_def).lower():
                                content_uses_spot = True

                    if not content_uses_spot:
                        continue

                    # Ensure ExtGState exists on the form
                    if xr is None:
                        xr = DictionaryObject()
                        xo[NameObject('/Resources')] = xr
                    if '/ExtGState' not in xr:
                        xr[NameObject('/ExtGState')] = DictionaryObject()
                    extg = xr['/ExtGState']
                    if hasattr(extg, 'get_object'):
                        extg = extg.get_object()

                    gs_dict = DictionaryObject()
                    gs_dict.update({
                        NameObject('/Type'): NameObject('/ExtGState'),
                        NameObject('/OP'): BooleanObject(True),
                        NameObject('/op'): BooleanObject(True),
                        NameObject('/OPM'): NumberObject(1),
                    })
                    gs_ref = writer._add_object(gs_dict)
                    extg[NameObject('/GSop')] = gs_ref

                    # Prepend '/GSop gs' to the form stream
                    if hasattr(xo, 'get_data') and hasattr(xo, 'set_data'):
                        try:
                            current = xo.get_data()
                        except Exception:
                            current = b''
                        xo.set_data(b"/GSop gs\n" + current)
                        patched = True

                writer.add_page(page)

            if patched:
                with open(pdf_path, 'wb') as f:
                    writer.write(f)
            return True
        except Exception as e:
            print(f"Error ensuring overprint: {e}")
            return False

    @staticmethod
    def embed_all_fonts(pdf_path: str) -> bool:
        """
        Ensure all fonts are embedded using Ghostscript (if available).
        Rewrites the PDF in place when successful.
        
        Note: Ghostscript may introduce graphics state imbalances (q/Q operators).
        This method fixes any imbalances after embedding.
        """
        gs = shutil.which('gs') or shutil.which('ghostscript')
        if not gs:
            return False
        try:
            # Write to a temp file then replace in place
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp.close()
            args = [
                gs,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.6',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-dDetectDuplicateImages=true',
                '-dCompressFonts=true',
                '-dSubsetFonts=true',
                '-dEmbedAllFonts=true',
                '-sOutputFile=' + tmp.name,
                pdf_path,
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.getsize(tmp.name) > 0:
                os.replace(tmp.name, pdf_path)
                
                # Fix any q/Q imbalances introduced by Ghostscript
                from .q_Q_fixer import fix_q_Q_imbalance
                fix_q_Q_imbalance(pdf_path)
                
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def outline_all_fonts(pdf_path: str) -> bool:
        """
        Convert all text to vector outlines using Ghostscript (pdfwrite).
        Rewrites the PDF in place when successful.
        
        Note: Ghostscript may introduce graphics state imbalances (q/Q operators).
        This method fixes any imbalances after outlining.
        """
        gs = shutil.which('gs') or shutil.which('ghostscript')
        if not gs:
            return False
        try:
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp.close()
            args = [
                gs,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.6',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-dNoOutputFonts',
                '-sOutputFile=' + tmp.name,
                pdf_path,
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.getsize(tmp.name) > 0:
                os.replace(tmp.name, pdf_path)
                
                # Fix any q/Q imbalances introduced by Ghostscript
                from .q_Q_fixer import fix_q_Q_imbalance
                fix_q_Q_imbalance(pdf_path)
                
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def has_unembedded_fonts(pdf_path: str) -> bool:
        """
        Heuristic check: returns True if any font on any page lacks an embedded
        font file (FontFile/FontFile2/FontFile3) in its FontDescriptor.
        Also scans Form XObjects recursively.
        """
        try:
            reader = PdfReader(pdf_path)

            def fonts_unembedded_in_resources(resources) -> bool:
                if resources is None:
                    return False
                if hasattr(resources, 'get_object'):
                    resources = resources.get_object()
                # Check page/form fonts
                if resources and '/Font' in resources:
                    fonts = resources['/Font']
                    if hasattr(fonts, 'get_object'):
                        fonts = fonts.get_object()
                    for _, f in getattr(fonts, 'items', lambda: [])():
                        if hasattr(f, 'get_object'):
                            f = f.get_object()
                        desc = None
                        try:
                            desc = f.get('/FontDescriptor') if hasattr(f, 'get') else None
                            if hasattr(desc, 'get_object'):
                                desc = desc.get_object()
                        except Exception:
                            desc = None
                        if not desc:
                            return True
                        if not (desc.get('/FontFile') or desc.get('/FontFile2') or desc.get('/FontFile3')):
                            return True
                # Recurse into XObjects
                if resources and '/XObject' in resources:
                    xobjs = resources['/XObject']
                    if hasattr(xobjs, 'get_object'):
                        xobjs = xobjs.get_object()
                    for _, xo in getattr(xobjs, 'items', lambda: [])():
                        if hasattr(xo, 'get_object'):
                            xo = xo.get_object()
                        xr = xo.get('/Resources') if hasattr(xo, 'get') else None
                        if fonts_unembedded_in_resources(xr):
                            return True
                return False

            for page in reader.pages:
                res = page.get('/Resources') if hasattr(page, 'get') else None
                if fonts_unembedded_in_resources(res):
                    return True
            return False
        except Exception:
            # If detection fails, do not force outlining by default
            return False

    @staticmethod
    def rotate_pdf(
        input_path: str,
        output_path: str,
        angle: int,
        flatten: bool = False,
    ) -> bool:
        """
        Rotate all pages by the given angle (0/90/180/270) and write to output.
        Uses PyMuPDF to transform page content. When flatten=True, the rotation
        is applied into the page coordinate space so downstream consumers see
        the updated mediabox/trimbox with swapped dimensions.
        """
        try:
            if angle not in {0, 90, 180, 270}:
                raise ValueError(f"angle must be one of {{0, 90, 180, 270}}, got {angle}")
                
            src = fitz.open(input_path)
            dst = fitz.open()
            
            # Carry over metadata if possible
            try:
                dst.set_metadata(src.metadata)
            except Exception:
                pass
            
            for page in src:
                rect = page.rect
                
                # Get original boxes if they exist
                original_trimbox = None
                original_bleedbox = None
                original_artbox = None
                try:
                    original_trimbox = page.trimbox
                except Exception:
                    pass
                try:
                    original_bleedbox = page.bleedbox
                except Exception:
                    pass
                try:
                    original_artbox = page.artbox
                except Exception:
                    pass
                
                if flatten and angle in (90, 270):
                    # Swap width/height for 90/270 degree rotations when flattening
                    target_width = rect.height
                    target_height = rect.width
                else:
                    target_width = rect.width
                    target_height = rect.height

                new_page = dst.new_page(width=target_width, height=target_height)
                new_page.show_pdf_page(new_page.rect, src, page.number, rotate=angle)
                
                # Helper function to rotate a box
                def rotate_box(box, orig_width, orig_height, rot_angle):
                    """Rotate a box by the given angle."""
                    if rot_angle == 90:
                        # Rotate 90° clockwise: (x, y) -> (y, original_width - x)
                        return fitz.Rect(
                            box.y0,  # new x0 = original y0
                            orig_width - box.x1,  # new y0 = original_width - original x1
                            box.y1,  # new x1 = original y1
                            orig_width - box.x0   # new y1 = original_width - original x0
                        )
                    elif rot_angle == 270:
                        # Rotate 270° clockwise (or 90° counter-clockwise)
                        # (x, y) -> (original_height - y, x)
                        return fitz.Rect(
                            orig_height - box.y1,  # new x0
                            box.x0,  # new y0
                            orig_height - box.y0,  # new x1
                            box.x1   # new y1
                        )
                    elif rot_angle == 180:
                        # Rotate 180°
                        # (x, y) -> (original_width - x, original_height - y)
                        return fitz.Rect(
                            orig_width - box.x1,
                            orig_height - box.y1,
                            orig_width - box.x0,
                            orig_height - box.y0
                        )
                    else:  # angle == 0
                        return box
                
                # Preserve boxes after rotation
                if flatten:
                    original_width = rect.width
                    original_height = rect.height
                    
                    # Preserve trimbox
                    if original_trimbox:
                        new_trimbox = rotate_box(original_trimbox, original_width, original_height, angle)
                        try:
                            new_page.set_trimbox(new_trimbox)
                        except Exception:
                            try:
                                new_page.set_cropbox(new_trimbox)
                            except Exception:
                                pass
                    
                    # Preserve bleedbox
                    if original_bleedbox:
                        new_bleedbox = rotate_box(original_bleedbox, original_width, original_height, angle)
                        try:
                            new_page.set_bleedbox(new_bleedbox)
                        except Exception:
                            pass
                    
                    # Preserve artbox
                    if original_artbox:
                        new_artbox = rotate_box(original_artbox, original_width, original_height, angle)
                        try:
                            new_page.set_artbox(new_artbox)
                        except Exception:
                            pass

            # Save with compression and cleanup
            dst.save(output_path, deflate=True, garbage=4, clean=True)
            dst.close()
            src.close()
            return True
        except Exception as e:
            print(f"Error rotating PDF: {e}")
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
    def embed_all_fonts(pdf_path: str) -> bool:
        """
        Ensure all fonts are embedded using Ghostscript (if available).
        Rewrites the PDF in place when successful.
        """
        gs = shutil.which('gs') or shutil.which('ghostscript')
        if not gs:
            return False
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp.close()
            args = [
                gs,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.6',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-dDetectDuplicateImages=true',
                '-dCompressFonts=true',
                '-dSubsetFonts=true',
                '-dEmbedAllFonts=true',
                '-sOutputFile=' + tmp.name,
                pdf_path,
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.getsize(tmp.name) > 0:
                os.replace(tmp.name, pdf_path)
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def outline_all_fonts(pdf_path: str) -> bool:
        """
        Convert all text to vector outlines using Ghostscript (pdfwrite).
        Rewrites the PDF in place when successful.
        """
        gs = shutil.which('gs') or shutil.which('ghostscript')
        if not gs:
            return False
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp.close()
            args = [
                gs,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.6',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-dNoOutputFonts',
                '-sOutputFile=' + tmp.name,
                pdf_path,
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.getsize(tmp.name) > 0:
                os.replace(tmp.name, pdf_path)
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def has_unembedded_fonts(pdf_path: str) -> bool:
        """
        Heuristic check: returns True if any font on any page lacks an embedded
        font file (FontFile/FontFile2/FontFile3) in its FontDescriptor.
        Also scans Form XObjects recursively.
        """
        try:
            reader = PdfReader(pdf_path)
            
            def check_resources(resources):
                if resources is None:
                    return False
                font_dict = resources.get('/Font')
                if font_dict:
                    for font_name, font_obj in font_dict.items():
                        try:
                            font = font_obj.get_object() if hasattr(font_obj, 'get_object') else font_obj
                            descriptor = font.get('/FontDescriptor')
                            if descriptor:
                                desc = descriptor.get_object() if hasattr(descriptor, 'get_object') else descriptor
                                # Check for embedded font file
                                if not any(key in desc for key in ['/FontFile', '/FontFile2', '/FontFile3']):
                                    return True
                        except Exception:
                            pass
                # Recurse into XObjects
                xobject_dict = resources.get('/XObject')
                if xobject_dict:
                    for xobj_name, xobj in xobject_dict.items():
                        try:
                            xobj_resolved = xobj.get_object() if hasattr(xobj, 'get_object') else xobj
                            if xobj_resolved.get('/Subtype') == '/Form':
                                xobj_resources = xobj_resolved.get('/Resources')
                                if check_resources(xobj_resources):
                                    return True
                        except Exception:
                            pass
                return False
            
            for page in reader.pages:
                resources = page.get('/Resources')
                if check_resources(resources):
                    return True
            return False
        except Exception:
            return False

