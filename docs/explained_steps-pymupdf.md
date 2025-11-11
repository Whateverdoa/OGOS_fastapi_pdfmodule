# PyMuPDF Compound-Path Workflow – Step by Step

This guide distils the live code path that now powers the OGOS FastAPI module. It expands on the original research notes with the exact responsibilities of each component so new contributors can reason about the pipeline quickly.

## 1. Analyse the Input Page

`PDFAnalyzer.analyze_pdf` inspects the first page using both PyMuPDF (`fitz`) and pypdf:

1. **Geometry** – Convert media/trim boxes into millimetres for consistent reporting.
2. **Dieline Detection** – `page.get_drawings()` still drives `detected_dielines`, but we additionally call `page.get_cdrawings()` to build the richer `dieline_layers` diagnostics.
3. **Layer Reporting** – Each stroke-only drawing contributes a segment:
   - `layer` – the optional-content group name (falls back to `unnamed`).
   - `stroke_color` – device-space colour tuple rounded to four decimals.
   - `line_width` – millimetres when PyMuPDF reports a width.
   - `bounding_box` – axis-aligned rectangle in millimetres.
4. **Mismatch Flag** – We lowercase/strip layer names and compare them against the canonical alias set (`stans`, `cutcontour`, `kisscut`, `diecut`). A mismatch is raised when more than one canonical alias appears or when aliases mix with unnamed layers. This is the signal consumed by the API headers.

> **Tip:** You can inspect the same structure via `python -m tools.dump_dieline path/to.pdf --json`.

## 2. Normalise Spot Colours

Before we touch geometry, the existing `SpotColorRenamer` and `SpotColorHandler` ensure that every Separation/DeviceN spot colour token matches `job_config.spot_color_name` (default `/stans`). They recurse into Form XObjects, `/OCProperties`, and content streams so that the later PyMuPDF pass only has to deal with geometry.

## 3. Merge Dieline Segments with PyMuPDF

`PyMuPDFCompoundPathTool.process` performs three major steps:

1. **Collect Streams** – Use pypdf to locate page and Form XObject content streams that reference our target spot-colour names. Each candidate stream is opened via `doc.xref_stream(xref)`.
2. **Extract Vector Sequences** – Delegate to `StansCompoundPathConverter` to strip unrelated content and retrieve raw operator sequences belonging to `/stans` strokes.
3. **Rebuild Primary Stream** – Insert the combined compound-path commands into the first stream, update any siblings to remove the redundant stroke blocks, and save with `doc.save(..., deflate=True)`.

The merged path inherits stroke width, graphics-state, and colour commands from the first matching sequence to keep overprint and optional content intact.

## 4. Post-Processing & Output

Once the compound path is committed, the tool runs one more pass to ensure the `/stans` spot colour carries the expected tint transform (100 % magenta) and 0.5 pt width. At this point the caller (either the API or CLI) can distribute the PDF.

## 5. Surfacing Diagnostics

The updated API surfaces the new information in three places:

| Location | What you get |
| --- | --- |
| `analysis.dieline_layers` | Full segment list and `layer_mismatch` boolean. |
| HTTP Headers | `X-Dieline-Layer-Mismatch`, `X-Dieline-Segment-Count`, and the existing winding metadata. |
| CLI | `python -m tools.dump_dieline` for humans, `/process?return_json=true` for automation. |

This ensures both manual QA and workflow automation can flag files where designers split dielines across multiple layers.

## 6. Extending the Workflow

When adding new capabilities, keep the following guidelines in mind:

- **Respect Geometry** – All PyMuPDF operations should use the original coordinates. Avoid snapping unless you also report the adjustment in diagnostics.
- **Layer Integrity** – If you introduce new form XObjects or redraw shapes, copy over the `/OCG` references from the original stream to avoid breaking layer toggles.
- **Testing** – Extend `tests/test_api_dieline_layers.py` (for API commitments) or build fixture-based tests when touching the compound-path tool.
- **CLI Affordances** – Prefer adding small flags to `tools.dump_dieline` over building ad-hoc scripts; this keeps QA workflows consistent.

## 7. Useful References

- `app/utils/pymupdf_compound_path_tool.py`
- `app/core/pdf_analyzer.py`
- `app/utils/stans_compound_path_converter.py`
- PyMuPDF documentation: [https://pymupdf.readthedocs.io](https://pymupdf.readthedocs.io)
