from pathlib import Path
import shutil
import tempfile
from typing import Dict, List, Optional, Set

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)


class SpotColorHandler:
    """Handles spot color manipulation in PDFs"""

    OVERPRINT_STATE_NAME = '/GS_STANS_OP'

    def __init__(self):
        self.target_spot_colors = [
            'CutContour', 'KissCut', 'Kiss Cut', 'Cut Contour',
            'cutcontour', 'kisscut', 'kiss cut', 'cut contour',
            'stans', 'Stans', 'STANS',
            'DieCut', 'diecut', 'Die Cut', 'die cut'
        ]
        
    def rename_spot_color(self, pdf_path: str, output_path: str, new_color_name: str = "stans") -> bool:
        """
        Rename spot colors in a PDF to a new name
        
        Args:
            pdf_path: Input PDF path
            output_path: Output PDF path
            new_color_name: New name for the spot color
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Open with PyMuPDF for analysis
            doc = fitz.open(pdf_path)
            
            # Create a new PDF with renamed spot colors
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Get the page's resources
                resources = page.get_contents()
                
                # TODO: This is a simplified version. In production, we would need to:
                # 1. Parse the content stream to find color space usage
                # 2. Update the color space definitions
                # 3. Replace references to old spot color names with new ones
                
            doc.save(output_path)
            doc.close()
            
            return True
            
        except Exception as e:
            print(f"Error renaming spot color: {e}")
            return False
            
    def update_spot_color_properties(
        self,
        pdf_path: str,
        output_path: str,
        spot_color_name: str,
        line_thickness: float = 0.5
    ) -> bool:
        """
        Update spot color properties (ensure 100% magenta, overprint)
        
        Args:
            pdf_path: Input PDF path
            output_path: Output PDF path
            spot_color_name: Name of the spot color to update
            line_thickness: Line thickness in points
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()

            target_cs_names: Set[str] = set()
            self._visited_streams: Set[int] = set()

            for page in reader.pages:
                resources = page.get('/Resources')
                self._enforce_properties_in_resources(
                    resources,
                    spot_color_name,
                    target_cs_names,
                )
                self._update_line_thickness_for_spot_paths(
                    page,
                    target_cs_names,
                    line_thickness,
                )
                writer.add_page(page)

            destination = Path(output_path)
            tmp_path: Optional[Path] = None
            if Path(pdf_path) == destination:
                tmp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                tmp_path = Path(tmp_file.name)
                tmp_file.close()
                target_handle = tmp_path.open('wb')
            else:
                target_handle = destination.open('wb')

            with target_handle as output_file:
                writer.write(output_file)

            if tmp_path is not None:
                shutil.move(str(tmp_path), str(destination))

            return True

        except Exception as e:
            print(f"Error updating spot color properties: {e}")
            return False
            
    def remove_dieline_paths(self, pdf_path: str, output_path: str) -> bool:
        """
        Remove existing CutContour dieline paths from a PDF using production-ready content stream parsing
        
        Args:
            pdf_path: Input PDF path
            output_path: Output PDF path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from .pdf_content_parser import PDFContentParser
            
            # Use production-ready content stream parser
            parser = PDFContentParser()
            success = parser.remove_cutcontour_paths(pdf_path, output_path)
            
            if success:
                # Verify the removal worked
                verification = parser.verify_removal(output_path)
                print(f"CutContour removal verification:")
                print(f"  Color spaces remaining: {verification.get('cutcontour_colorspaces', 0)}")
                print(f"  Content references remaining: {verification.get('cutcontour_references', 0)}")
                
                if verification.get('cutcontour_colorspaces', 0) == 0 and verification.get('cutcontour_references', 0) == 0:
                    print("✅ CutContour completely removed from PDF")
                else:
                    print("⚠️ Some CutContour elements may remain")
            
            return success
            
        except Exception as e:
            print(f"Error removing dieline paths: {e}")
            return False

    # ------------------------------------------------------------------
    # Spot color enforcement helpers
    # ------------------------------------------------------------------
    def _enforce_properties_in_resources(
        self,
        resources,
        spot_color_name: str,
        target_cs_names: Set[str],
    ) -> None:
        res_obj = self._resolve(resources)
        if not res_obj:
            return

        color_spaces = res_obj.get('/ColorSpace')
        if color_spaces:
            color_spaces_obj = self._resolve(color_spaces)
            for cs_name, cs_def in list(color_spaces_obj.items()):
                normalized, is_target = self._normalize_separation_colorspace(
                    cs_def,
                    spot_color_name,
                )
                if is_target:
                    target_name = str(cs_name)
                    if not target_name.startswith('/'):
                        target_name = f'/{target_name}'
                    target_cs_names.add(target_name)
                if normalized is not None:
                    color_spaces_obj[NameObject(str(cs_name))] = normalized

        extgstate = res_obj.get('/ExtGState')
        if extgstate:
            extgstate_obj = self._resolve(extgstate)
            # Only create the dieline-specific overprint ExtGState, don't modify existing ones
            # Overprint will be applied selectively via content stream rewriting for dieline strokes only
            overprint_key = NameObject(self.OVERPRINT_STATE_NAME)
            if overprint_key not in extgstate_obj:
                extgstate_obj[overprint_key] = self._build_overprint_extgstate()

        xobjects = res_obj.get('/XObject')
        if xobjects:
            xobjects_obj = self._resolve(xobjects)
            for child in xobjects_obj.values():
                child_obj = self._resolve(child)
                if isinstance(child_obj, DictionaryObject):
                    self._enforce_properties_in_resources(
                        child_obj.get('/Resources'),
                        spot_color_name,
                        target_cs_names,
                    )

    def _normalize_separation_colorspace(
        self,
        colorspace,
        spot_color_name: str,
    ) -> (Optional[ArrayObject], bool):
        target = self._resolve(colorspace)
        if not isinstance(target, ArrayObject) or len(target) < 4:
            return None, False

        if str(target[0]) != '/Separation':
            return None, False

        color_token = str(target[1])
        color_lower = color_token.lstrip('/').lower()
        should_normalize = (
            color_lower == spot_color_name.lower()
            or color_lower in {name.lower() for name in self.target_spot_colors}
        )

        if not should_normalize:
            return None, False

        normalized = ArrayObject([
            NameObject('/Separation'),
            NameObject(f'/{spot_color_name}'),
            NameObject('/DeviceCMYK'),
            self._build_magenta_tint_function(),
        ])
        return normalized, True

    def _build_magenta_tint_function(self) -> DictionaryObject:
        return DictionaryObject({
            NameObject('/FunctionType'): NumberObject(2),
            NameObject('/Domain'): ArrayObject([FloatObject(0), FloatObject(1)]),
            NameObject('/C0'): ArrayObject([
                FloatObject(0),
                FloatObject(0),
                FloatObject(0),
                FloatObject(0),
            ]),
            NameObject('/C1'): ArrayObject([
                FloatObject(0),
                FloatObject(1),
                FloatObject(0),
                FloatObject(0),
            ]),
            NameObject('/N'): NumberObject(1),
        })

    def _build_overprint_extgstate(self) -> DictionaryObject:
        return DictionaryObject({
            NameObject('/Type'): NameObject('/ExtGState'),
            NameObject('/OP'): BooleanObject(True),
            NameObject('/op'): BooleanObject(True),
            NameObject('/OPM'): NumberObject(1),
        })

    def _update_line_thickness_for_spot_paths(
        self,
        container,
        spot_cs_names: Set[str],
        line_thickness: float,
    ) -> None:
        if not spot_cs_names:
            return

        streams = []
        resources = None

        if hasattr(container, 'get_data'):
            streams.append(self._resolve(container))
            resources = container.get('/Resources') if hasattr(container, 'get') else None
        elif isinstance(container, DictionaryObject):
            if '/Contents' not in container:
                return
            contents = container['/Contents']
            if isinstance(contents, list):
                for stream in contents:
                    streams.append(self._resolve(stream))
            else:
                streams.append(self._resolve(contents))
            resources = container.get('/Resources')

        self._update_child_streams(resources, spot_cs_names, line_thickness)

        for stream in streams:
            if stream is None or not hasattr(stream, 'get_data'):
                continue
            try:
                original = stream.get_data().decode('latin-1')
            except Exception:
                continue
            updated = self._rewrite_line_thickness(
                original,
                spot_cs_names,
                line_thickness,
            )
            if updated != original:
                stream.set_data(updated.encode('latin-1'))

    def _rewrite_line_thickness(
        self,
        content_text: str,
        spot_cs_names: Set[str],
        line_thickness: float,
    ) -> str:
        lines = content_text.split('\n')
        cs_tokens = {name for name in spot_cs_names}
        cs_tokens.update({name.lower() for name in spot_cs_names})
        cs_tokens.update({name.upper() for name in spot_cs_names})

        formatted_w = f"{self._format_pdf_number(line_thickness)} w"
        overprint_line = f"{self.OVERPRINT_STATE_NAME} gs"

        active_cs = None
        last_gs_index: Optional[int] = None
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue

            tokens = stripped.split()
            if len(tokens) == 2 and tokens[1] in {'CS', 'cs'}:
                name_token = tokens[0]
                if not name_token.startswith('/'):
                    name_token = f'/{name_token}'
                if name_token in cs_tokens:
                    active_cs = name_token
                else:
                    active_cs = None
                last_gs_index = None
                i += 1
                continue

            if len(tokens) == 2 and tokens[1] == 'gs':
                name_token = tokens[0]
                if not name_token.startswith('/'):
                    name_token = f'/{name_token}'
                last_gs_index = i
                i += 1
                continue

            if active_cs and tokens[-1] in {'SCN', 'scn'}:
                if last_gs_index is not None:
                    lines[last_gs_index] = overprint_line
                else:
                    lines.insert(i, overprint_line)
                    i += 1
                    last_gs_index = i - 1

                insert_index = i + 1
                while insert_index < len(lines) and not lines[insert_index].strip():
                    insert_index += 1

                if insert_index < len(lines) and lines[insert_index].strip().endswith(' w'):
                    lines[insert_index] = formatted_w
                else:
                    lines.insert(i + 1, formatted_w)
                    i += 1
                active_cs = None
                last_gs_index = None
                i += 1
                continue

            i += 1

        return '\n'.join(lines)

    def _format_pdf_number(self, value: float) -> str:
        if abs(value) < 1e-9:
            return '0'
        return f"{value:g}"

    def _resolve(self, value):
        if hasattr(value, 'get_object'):
            try:
                return value.get_object()
            except Exception:
                return None
        return value

    def _update_child_streams(
        self,
        resources,
        spot_cs_names: Set[str],
        line_thickness: float,
    ) -> None:
        res_obj = self._resolve(resources)
        if not res_obj:
            return

        xobjects = res_obj.get('/XObject')
        if not xobjects:
            return

        xobjects_obj = self._resolve(xobjects)
        if not xobjects_obj:
            return

        for child in xobjects_obj.values():
            child_obj = self._resolve(child)
            if not child_obj or not hasattr(child_obj, 'get_data'):
                continue
            identity = id(child_obj)
            if identity in getattr(self, '_visited_streams', set()):
                continue
            self._visited_streams.add(identity)

            child_resources = child_obj.get('/Resources')
            child_names = set(spot_cs_names)
            child_names.update(self._collect_colorspace_names(child_resources))

            self._update_line_thickness_for_spot_paths(
                child_obj,
                child_names,
                line_thickness,
            )

    def _collect_colorspace_names(self, resources) -> Set[str]:
        names: Set[str] = set()
        res_obj = self._resolve(resources)
        if not res_obj:
            return names
        color_spaces = res_obj.get('/ColorSpace')
        if not color_spaces:
            return names
        color_spaces_obj = self._resolve(color_spaces)
        if not color_spaces_obj:
            return names
        for cs_name in color_spaces_obj.keys():
            names.add(str(cs_name))
        return names
