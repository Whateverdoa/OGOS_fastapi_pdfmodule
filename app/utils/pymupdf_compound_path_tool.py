from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

import fitz
from pypdf import PdfReader
from pypdf.generic import DictionaryObject, IndirectObject

from .stans_compound_path_converter import StansCompoundPathConverter
from .spot_color_handler import SpotColorHandler
from .spot_color_renamer import SpotColorRenamer


@dataclass
class CompoundPathResult:
    """Represents the outcome of the PyMuPDF compound-path pass."""

    xrefs_processed: List[int]
    sequences_removed: int
    sequences_combined: int


class PyMuPDFCompoundPathTool:
    """Combine stans dieline segments inside Form XObjects using PyMuPDF."""

    def __init__(self) -> None:
        self.converter = StansCompoundPathConverter()

    def process(self, input_path: str, output_path: Optional[str] = None) -> CompoundPathResult:
        """Combine dieline segments and write the updated PDF."""

        reader = PdfReader(input_path)
        doc = fitz.open(input_path)

        page = reader.pages[0]
        stans_names = self.converter._find_stans_colorspaces_in_resources(page.get('/Resources'))

        xrefs: List[Tuple[int, Set[str]]] = []
        xrefs.extend(self._collect_page_streams(page, stans_names))
        xrefs.extend(self._collect_form_xrefs(page.get('/Resources'), stans_names))
        default_color = next(iter(stans_names)) if stans_names else None

        extractions = {}
        all_sequences: List[List[str]] = []

        for xref, names in xrefs:
            if not names:
                continue
            try:
                original = doc.xref_stream(xref).decode('latin-1')
            except Exception:
                continue

            filtered_lines, sequences, insertion_index = self.converter._extract_sequence_blocks(original, names)
            if not sequences:
                continue

            extractions[xref] = {
                'filtered_lines': filtered_lines,
                'insertion_index': insertion_index,
            }
            all_sequences.extend(sequences)

        total_sequences = len(all_sequences)
        if total_sequences <= 1:
            target_path = output_path or input_path
            doc.close()
            self._normalize_spot_colour(target_path)
            return CompoundPathResult([], 0, 0)

        processed_xrefs: List[int] = list(extractions.keys())

        primary_xref = processed_xrefs[0]
        compound_lines = self._build_compound_lines_from_sequences(all_sequences, default_color)
        if not compound_lines:
            doc.close()
            return CompoundPathResult([], 0, 0)

        for xref, info in extractions.items():
            filtered_lines = list(info['filtered_lines'])
            if xref == primary_xref:
                continue
            doc.update_stream(xref, '\n'.join(filtered_lines).encode('latin-1'))

        primary_info = extractions[primary_xref]
        primary_lines = list(primary_info['filtered_lines'])
        insertion_index = primary_info['insertion_index']
        if insertion_index is None:
            insertion_index = len(primary_lines)
        primary_lines[insertion_index:insertion_index] = compound_lines
        doc.update_stream(primary_xref, '\n'.join(primary_lines).encode('latin-1'))

        target_path = output_path or input_path
        doc.save(target_path, deflate=True)
        doc.close()

        self._normalize_spot_colour(target_path)

        return CompoundPathResult(
            xrefs_processed=processed_xrefs,
            sequences_removed=total_sequences,
            sequences_combined=1,
        )
    def _build_compound_lines_from_sequences(
        self,
        sequences: List[List[str]],
        default_color: Optional[str],
    ) -> List[str]:
        if not sequences:
            return []

        fmt = StansCompoundPathConverter._format_pdf_number

        color_lines: List[str] = []
        gs_line: Optional[str] = None
        width_value: Optional[float] = None
        path_lines: List[str] = []

        for seq in sequences:
            matrix_stack: List[List[float]] = []
            current_matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]

            for line in seq:
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped == 'q':
                    matrix_stack.append(current_matrix[:])
                    continue
                if stripped == 'Q':
                    current_matrix = matrix_stack.pop() if matrix_stack else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                    continue

                tokens = stripped.split()
                op = tokens[-1]

                if op == 'cm' and len(tokens) == 7:
                    values = list(map(float, tokens[:-1]))
                    current_matrix = self._matrix_multiply(current_matrix, values)
                    continue

                if op in {'CS', 'cs', 'SC', 'sc', 'SCN', 'scn'}:
                    if stripped not in color_lines:
                        color_lines.append(stripped)
                    continue

                if op == 'gs' and gs_line is None:
                    gs_line = stripped
                    continue

                if op == 'w' and width_value is None and len(tokens) >= 2:
                    try:
                        width_value = float(tokens[0])
                    except ValueError:
                        pass
                    continue

                if op == 'm' and len(tokens) >= 3:
                    x, y = map(float, tokens[:-1])
                    x, y = self._apply_matrix(current_matrix, x, y)
                    path_lines.append(f"{fmt(x)} {fmt(y)} m")
                elif op == 'l' and len(tokens) >= 3:
                    x, y = map(float, tokens[:-1])
                    x, y = self._apply_matrix(current_matrix, x, y)
                    path_lines.append(f"{fmt(x)} {fmt(y)} l")
                elif op == 'c' and len(tokens) >= 7:
                    coords = list(map(float, tokens[:-1]))
                    p1x, p1y = self._apply_matrix(current_matrix, coords[0], coords[1])
                    p2x, p2y = self._apply_matrix(current_matrix, coords[2], coords[3])
                    p3x, p3y = self._apply_matrix(current_matrix, coords[4], coords[5])
                    path_lines.append(
                        f"{fmt(p1x)} {fmt(p1y)} {fmt(p2x)} {fmt(p2y)} {fmt(p3x)} {fmt(p3y)} c"
                    )
                elif op == 'h':
                    path_lines.append('h')
                elif op == 're' and len(tokens) >= 5:
                    x, y, w, h = map(float, tokens[:-1])
                    corners = [
                        (x, y),
                        (x + w, y),
                        (x + w, y + h),
                        (x, y + h),
                    ]
                    transformed = [self._apply_matrix(current_matrix, px, py) for px, py in corners]
                    start = transformed[0]
                    path_lines.append(f"{fmt(start[0])} {fmt(start[1])} m")
                    for px, py in transformed[1:]:
                        path_lines.append(f"{fmt(px)} {fmt(py)} l")
                    path_lines.append('h')
                else:
                    # ignore other operators like S, n, k, etc.
                    continue

        if not path_lines:
            return []

        lines: List[str] = ['q']
        if color_lines:
            lines.extend(color_lines)
        elif default_color:
            token = default_color if default_color.startswith('/') else f'/{default_color}'
            lines.append(f'{token} CS')
            lines.append('1 SCN')
        else:
            lines.append('/CS2 CS')
            lines.append('1 SCN')

        if width_value is not None:
            lines.append(f"{fmt(width_value)} w")

        if gs_line:
            lines.append(gs_line)

        lines.extend(path_lines)
        lines.append('S')
        lines.append('Q')
        return lines

    def _matrix_multiply(self, a: List[float], b: List[float]) -> List[float]:
        return [
            a[0] * b[0] + a[2] * b[1],
            a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3],
            a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4],
            a[1] * b[4] + a[3] * b[5] + a[5],
        ]

    def _apply_matrix(self, matrix: List[float], x: float, y: float) -> Tuple[float, float]:
        new_x = matrix[0] * x + matrix[2] * y + matrix[4]
        new_y = matrix[1] * x + matrix[3] * y + matrix[5]
        return new_x, new_y

    def _normalize_spot_colour(self, pdf_path: str) -> None:
        renamer = SpotColorRenamer()
        handler = SpotColorHandler()

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            temp_path = tmp_file.name

        try:
            # Rename all dieline separations to /stans
            if renamer.rename_cutcontour_to_stans(pdf_path, temp_path, 'stans'):
                shutil.move(temp_path, pdf_path)
            else:
                os.unlink(temp_path)

            # Enforce stroke properties (100% magenta, 0.5pt, overprint)
            handler.update_spot_color_properties(pdf_path, pdf_path, 'stans', line_thickness=0.5)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _collect_page_streams(self, page, stans_names: Set[str]) -> List[Tuple[int, Set[str]]]:
        xrefs: List[Tuple[int, Set[str]]] = []

        contents = page.get('/Contents')
        if contents is None:
            return xrefs

        if isinstance(contents, list):
            for stream in contents:
                xref = self._xref_for(stream)
                if xref is not None:
                    xrefs.append((xref, set(stans_names)))
        else:
            xref = self._xref_for(contents)
            if xref is not None:
                xrefs.append((xref, set(stans_names)))

        return xrefs

    def _collect_form_xrefs(self, resources, inherited_names: Set[str]) -> List[Tuple[int, Set[str]]]:
        results: List[Tuple[int, Set[str]]] = []
        if not resources:
            return results

        try:
            res_obj = resources.get_object() if hasattr(resources, 'get_object') else resources
        except Exception:
            return results

        if not isinstance(res_obj, DictionaryObject):
            return results

        xobjects = res_obj.get('/XObject')
        if not xobjects:
            return results

        for name, value in xobjects.items():
            form = value.get_object() if isinstance(value, IndirectObject) else value
            if not isinstance(form, DictionaryObject):
                continue

            if form.get('/Subtype') != '/Form':
                continue

            xref = self._xref_for(value)
            if xref is None:
                continue

            local_names = set(inherited_names)
            local_names.update(self.converter._find_stans_colorspaces_in_resources(form.get('/Resources')))

            results.append((xref, local_names))
            results.extend(self._collect_form_xrefs(form.get('/Resources'), local_names))

        return results

    def _xref_for(self, obj) -> Optional[int]:
        if isinstance(obj, IndirectObject):
            return obj.idnum
        return None
