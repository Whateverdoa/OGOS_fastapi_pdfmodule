from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, ArrayObject, DictionaryObject, IndirectObject


class StansCompoundPathConverter:
    """Convert multi-segment stans dielines into a single compound path."""

    TARGET_COLOR_NAMES = {
        'stans',
        'stanslijn',
        'cutcontour',
        'kisscut',
        'diecut',
    }

    PAINT_OPERATORS = {
        'S', 's', 'B', 'b', 'B*', 'b*', 'F', 'f', 'F*', 'f*', 'n'
    }

    def __init__(self) -> None:
        self.debug = False
        self._processed_xobjects: Set[int] = set()

    def ensure_compound_paths(self, input_path: str, output_path: str) -> Dict[str, object]:
        """Ensure all stans dielines are rendered as a single compound path."""
        result: Dict[str, object] = {
            'success': False,
            'pages_processed': 0,
            'stans_sequences_found': 0,
            'compound_paths_created': 0,
            'error': None,
        }

        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()
            self._processed_xobjects: Set[int] = set()

            for page in reader.pages:
                stans_colorspaces = self._find_stans_colorspaces_in_resources(page.get('/Resources'))
                if stans_colorspaces:
                    page_stats = self._merge_stans_sequences(page, stans_colorspaces)
                    result['stans_sequences_found'] += page_stats['stans_sequences_found']
                    result['compound_paths_created'] += page_stats['compound_paths_created']
                writer.add_page(page)
                result['pages_processed'] += 1

            with open(output_path, 'wb') as output_file:
                writer.write(output_file)

            result['success'] = True
            return result

        except Exception as exc:  # pragma: no cover - defensive
            result['error'] = str(exc)
            if self.debug:
                print(f"Failed to build compound path: {exc}")
            return result

    # ------------------------------------------------------------------
    # Colorspace helpers
    # ------------------------------------------------------------------
    def _find_stans_colorspaces_in_resources(self, resources) -> Set[str]:
        names: Set[str] = set()
        res_obj = self._resolve(resources)
        if not res_obj:
            return names

        try:
            color_spaces = res_obj.get('/ColorSpace')
            if not color_spaces:
                return names
            color_spaces_obj = self._resolve(color_spaces)
            if not color_spaces_obj:
                return names
            for cs_name, cs_def in color_spaces_obj.items():
                color_name = self._identify_color_from_colorspace(cs_name, cs_def)
                if color_name:
                    names.add(str(cs_name))
        except Exception as exc:  # pragma: no cover - defensive
            if self.debug:
                print(f"Colorspace inspection failed: {exc}")
        return names

    def _identify_color_from_colorspace(self, cs_name, cs_def) -> Optional[str]:
        try:
            if hasattr(cs_def, 'get_object'):
                cs_def = cs_def.get_object()

            definition = str(cs_def)
            lowered = definition.lower()
            for target in self.TARGET_COLOR_NAMES:
                if target in lowered:
                    return target

            if hasattr(cs_def, '__getitem__') and hasattr(cs_def, '__len__'):
                if len(cs_def) > 1 and str(cs_def[0]) == '/Separation':
                    color_name = str(cs_def[1]).replace('/', '').lower()
                    if color_name in self.TARGET_COLOR_NAMES:
                        return color_name
        except Exception as exc:  # pragma: no cover - defensive
            if self.debug:
                print(f"Failed to parse colorspace {cs_name}: {exc}")
        return None

    # ------------------------------------------------------------------
    # Content stream manipulation
    # ------------------------------------------------------------------
    def _merge_stans_sequences(self, page, stans_names: Set[str]) -> Dict[str, int]:
        stats = {
            'stans_sequences_found': 0,
            'compound_paths_created': 0,
        }

        if '/Contents' not in page:
            # Still descend into XObjects even if page has no contents
            self._process_child_xobjects(page.get('/Resources'), stans_names, stats)
            return stats

        contents = page['/Contents']
        if isinstance(contents, list):
            cleaned_streams = []
            for stream in contents:
                if hasattr(stream, 'get_object'):
                    stream_obj = stream.get_object()
                else:
                    stream_obj = stream
                stream_stats = self._process_stream(stream_obj, stans_names, page.get('/Resources'))
                stats['stans_sequences_found'] += stream_stats['stans_sequences_found']
                stats['compound_paths_created'] += stream_stats['compound_paths_created']
                cleaned_streams.append(stream_obj)
            page[NameObject('/Contents')] = ArrayObject(cleaned_streams)
        else:
            if hasattr(contents, 'get_object'):
                stream_obj = contents.get_object()
            else:
                stream_obj = contents
            stream_stats = self._process_stream(stream_obj, stans_names, page.get('/Resources'))
            stats['stans_sequences_found'] += stream_stats['stans_sequences_found']
            stats['compound_paths_created'] += stream_stats['compound_paths_created']
            page[NameObject('/Contents')] = stream_obj

        self._process_child_xobjects(page.get('/Resources'), stans_names, stats)

        return stats

    def _process_stream(self, content_stream, stans_names: Set[str], resources) -> Dict[str, int]:
        stats = {
            'stans_sequences_found': 0,
            'compound_paths_created': 0,
        }

        if not hasattr(content_stream, 'get_data'):
            return stats

        # Descend into child XObjects before mutating the current stream so nested
        # resources are normalised in place.
        child_stats = self._process_child_xobjects(resources, stans_names, None)
        if child_stats:
            stats['stans_sequences_found'] += child_stats['stans_sequences_found']
            stats['compound_paths_created'] += child_stats['compound_paths_created']

        try:
            content_text = content_stream.get_data().decode('latin-1')
        except Exception as exc:  # pragma: no cover - defensive
            if self.debug:
                print(f"Unable to decode content stream: {exc}")
            return stats

        updated_text, sequence_count, combined = self._combine_stans_sequences(content_text, stans_names)
        stats['stans_sequences_found'] += sequence_count

        # Only rewrite the stream when multiple stans sequences were actually
        # merged. Single sequences are already compound and should be left
        # untouched to avoid subtle content ordering changes.
        if combined and sequence_count > 1:
            if self.debug:
                print(f"Combined {sequence_count} stans sequences into compound path")
            encoded = updated_text.encode('latin-1')
            if hasattr(content_stream, 'set_data'):
                content_stream.set_data(encoded)
            else:
                content_stream._data = encoded
            stats['compound_paths_created'] += 1
        elif self.debug and sequence_count <= 1:
            print("Stans content already single path; no compound rewrite applied")

        return stats


    def _combine_stans_sequences(self, content_text: str, stans_names: Set[str]) -> Tuple[str, int, bool]:
        filtered_lines, sequences, insertion_index = self._extract_sequence_blocks(content_text, stans_names)

        sequence_count = len(sequences)
        if sequence_count <= 1:
            return content_text, sequence_count, False

        compound_sequence = self._build_compound_sequence(sequences)
        if not compound_sequence:
            return content_text, sequence_count, False

        if insertion_index is None:
            insertion_index = len(filtered_lines)
        filtered_lines[insertion_index:insertion_index] = compound_sequence

        updated_text = '\n'.join(filtered_lines)
        return updated_text, sequence_count, True

    def _extract_sequence_blocks(
        self,
        content_text: str,
        stans_names: Set[str],
    ) -> Tuple[List[str], List[List[str]], Optional[int]]:
        lines = content_text.split('\n')
        filtered_lines: List[str] = []
        sequences: List[List[str]] = []
        insertion_index: Optional[int] = None

        collecting = False
        current_sequence: List[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]

            if collecting:
                current_sequence.append(line)
                stripped = line.strip()
                if stripped in self.PAINT_OPERATORS:
                    if i + 1 < len(lines) and lines[i + 1].strip() == 'Q':
                        current_sequence.append(lines[i + 1])
                        i += 1
                    sequences.append(current_sequence)
                    collecting = False
                    current_sequence = []
                i += 1
                continue

            cs_name = self._extract_colorspace_name(line, stans_names)
            if cs_name:
                collecting = True
                prelude = self._pull_prelude(filtered_lines)
                if prelude:
                    current_sequence.extend(prelude)
                current_sequence.append(line)
                if insertion_index is None:
                    insertion_index = len(filtered_lines)
                i += 1
                continue

            filtered_lines.append(line)
            i += 1

        if collecting and current_sequence:
            filtered_lines.extend(current_sequence)

        return filtered_lines, sequences, insertion_index

    # ------------------------------------------------------------------
    # Sequence combination helpers
    # ------------------------------------------------------------------
    def _extract_colorspace_name(self, line: str, stans_names: Set[str]) -> Optional[str]:
        stripped = line.strip()
        if not stripped:
            return None

        tokens = stripped.split()
        if len(tokens) != 2:
            return None

        name_token, operator = tokens
        if operator not in {'CS', 'cs'}:
            return None

        if not name_token.startswith('/'):
            return None

        if name_token in stans_names:
            return name_token

        lowered = name_token.lstrip('/').lower()
        if lowered in self.TARGET_COLOR_NAMES:
            return name_token

        return None

    def _pull_prelude(self, filtered_lines: List[str]) -> List[str]:
        prelude: List[str] = []
        while filtered_lines:
            candidate = filtered_lines[-1]
            stripped = candidate.strip()
            if stripped == 'q' or stripped.endswith(' gs') or stripped.endswith(' cm'):
                prelude.append(filtered_lines.pop())
            else:
                break
        prelude.reverse()
        return prelude

    def _build_compound_sequence(self, sequences: List[List[str]]) -> List[str]:
        combined: List[str] = []
        color_setup: List[str] = []
        path_commands: List[str] = []
        trailing: List[str] = []
        stroke_operator: Optional[str] = None
        leading_q: Optional[str] = None
        trailing_q: Optional[str] = None

        for sequence in sequences:
            if not sequence:
                continue
            seq = list(sequence)
            # capture wrappers
            start_idx = 0
            if seq[0].strip() == 'q':
                if leading_q is None:
                    leading_q = seq[0]
                start_idx = 1
            end_trim = len(seq)
            if seq[-1].strip() == 'Q':
                trailing_q = seq[-1]
                end_trim -= 1

            stroke_idx = self._find_stroke_index(seq[:end_trim])
            if stroke_idx is None:
                continue
            path_start_idx = self._find_first_path_index(seq, start_idx, stroke_idx)
            if path_start_idx is None:
                continue

            color_part = seq[start_idx:path_start_idx]
            path_part = seq[path_start_idx:stroke_idx]
            post_part = seq[stroke_idx + 1:end_trim]

            if not color_setup:
                color_setup.extend(color_part)

            path_commands.extend(path_part)
            trailing.extend(post_part)

            if stroke_operator is None:
                stroke_operator = seq[stroke_idx]

        if not path_commands:
            return []

        combined.extend(item for item in (leading_q,) if item)
        combined.extend(color_setup)
        combined.extend(path_commands)
        if stroke_operator:
            combined.append(stroke_operator)
        combined.extend(self._dedupe_preserve_order(trailing))
        combined.extend(item for item in (trailing_q,) if item)

        return combined

    def _find_stroke_index(self, sequence: List[str]) -> Optional[int]:
        for idx, line in enumerate(sequence):
            if line.strip() in self.PAINT_OPERATORS:
                return idx
        return None

    def _find_first_path_index(self, sequence: List[str], start_idx: int, stroke_idx: int) -> Optional[int]:
        for idx in range(start_idx, stroke_idx):
            if self._is_path_command(sequence[idx]):
                return idx
        return None

    def _is_path_command(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        tokens = stripped.split()
        if not tokens:
            return False
        operator = tokens[-1]
        return operator in {'m', 'l', 'c', 'v', 'y', 'h', 're'}

    @staticmethod
    def _dedupe_preserve_order(items: List[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _format_pdf_number(value: float) -> str:
        if abs(value) < 1e-9:
            return '0'
        return f"{value:g}"

    def _process_child_xobjects(self, resources, stans_names: Set[str], stats: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        res_obj = self._resolve(resources)
        if not res_obj:
            return stats

        xobjects = res_obj.get('/XObject')
        if not xobjects:
            return stats

        xobjects_obj = self._resolve(xobjects)
        if not xobjects_obj:
            return stats

        if stats is None:
            stats = {
                'stans_sequences_found': 0,
                'compound_paths_created': 0,
            }

        for xobj_ref in xobjects_obj.values():
            xobj_obj = self._resolve(xobj_ref)
            if not xobj_obj or not hasattr(xobj_obj, 'get_data'):
                continue
            identifier = id(xobj_obj)
            if identifier in getattr(self, '_processed_xobjects', set()):
                continue
            self._processed_xobjects.add(identifier)

            child_resources = xobj_obj.get('/Resources')
            child_names = set(stans_names)
            child_names.update(self._find_stans_colorspaces_in_resources(child_resources))

            child_stats = self._process_stream(xobj_obj, child_names, child_resources)
            stats['stans_sequences_found'] += child_stats['stans_sequences_found']
            stats['compound_paths_created'] += child_stats['compound_paths_created']

        return stats

    def _resolve(self, value):
        if value is None:
            return None
        if hasattr(value, 'get_object'):
            try:
                return value.get_object()
            except Exception:
                return None
        return value
