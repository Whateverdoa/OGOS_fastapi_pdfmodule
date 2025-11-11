# PDF Dieline Colour & Layer Diagnostics

The PyMuPDF integration introduced richer metadata and tooling. This reference explains how to interpret the `dieline_layers` report and how it maps back to the PDF primitives (color spaces, optional-content groups, and streams).

## 1. What `dieline_layers` Exposes

Each segment reported by the analyzer is a snapshot of a stroke-only drawing that PyMuPDF classified as part of the dieline:

- `layer` – The optional-content group (OCG) name visible in Acrobat/Illustrator. When PyMuPDF cannot determine the name, we emit `unnamed`.
- `stroke_color` – A list of device colour components. For Separation/DeviceN spot colours, PyMuPDF supplies the fallback simulation (typically CMYK). Values are rounded to four decimals.
- `line_width` – Width in millimetres, allowing you to confirm whether source artwork respected the 0.5 pt standard.
- `bounding_box` – Axis-aligned bounds in millimetres. Pair this with the existing `detected_dielines` array when troubleshooting geometry.

The top-level `layer_mismatch` flag flips to `true` when either of the following occurs:

1. Multiple canonical dieline aliases appear (e.g., `/stans` and `/CutContour`).
2. Canonical aliases are mixed with unnamed layers (`layer` evaluated to `unnamed`).
3. Multiple distinct raw layer tokens were discovered, even if they map to the same canonical alias (defensive signal for unexpected input).

This diagnostic allows the API to set `X-Dieline-Layer-Mismatch` and helps operators flag jobs before they hit production presses.

## 2. Linking Diagnostics to PDF Internals

Use the following table to move between diagnostics and low-level structures when debugging.

| Diagnostic Field | PDF Source | Investigation Tips |
| --- | --- | --- |
| `layer` | `/Properties` entry referencing an `/OCG` in page or XObject resources. | Search the PDF for the OCG object (`/Type /OCG`) and confirm its `/Name` has been normalised to `/stans`. |
| `stroke_color` | `/ColorSpace` entry used by the stroke (`/Separation` or `/DeviceN`). | Ensure the second token in the colour-space array is `/stans`. The tint transform should remain unchanged. |
| `line_width` | Graphics state in the content stream (`w` operator). | The compound-path tool enforces 0.5 pt during the final normalisation pass. Values outside tolerance suggest the input PDF had multiple inconsistent segments. |
| `bounding_box` | Bounding box reported by PyMuPDF for the stroke. | Compare against the `detected_dielines` array or load the PDF in Illustrator to visualise the region. |

## 3. Debugging Workflow

1. **Run the Analyzer CLI**
   ```bash
   python -m tools.dump_dieline suspect.pdf --indent 2
   ```
   Check the mismatch flag and note any unexpected layer names or colour tuples.

2. **Inspect Resources (If Needed)**
   ```python
   from pypdf import PdfReader

   reader = PdfReader("suspect.pdf")
   page = reader.pages[0]
   print(page["/Resources"]["/ColorSpace"].keys())
   ```
   Drill into `/ColorSpace`, `/ExtGState`, and `/Properties` when the CLI output points to a problematic segment.

3. **Regenerate via CLI** (when manual fix is acceptable)
   ```bash
   python -m tools.pymupdf_compound_path suspect.pdf fixed.pdf
   ```
   Re-run the analyzer on `fixed.pdf` to confirm the mismatch has cleared.

4. **Automate via API** – Use `/api/pdf/process?return_json=true` to integrate the diagnostics into workflow automation. The JSON response contains the same `dieline_layers` structure along with the processed PDF in base64 form.

## 4. Common Issues & Resolutions

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `layer_mismatch=true` with `unnamed` segments | Designer omitted OCG metadata on some dieline paths. | Treat as a QA warning; the pipeline still merges paths, but operators should confirm intent. |
| Multiple segments share the same bounding box | Separate subpaths (outer shape + inner hole) were detected. | Expected; confirm both segments belong to the same canonical layer. |
| Colour tuple deviates from `[0.0, 1.0, 0.0, 0.0]` | Input PDF used a different fallback (e.g., RGB or a richer DeviceN). | After processing, re-run the analyzer to confirm the final PDF reports the standard CMYK values. |
| Headers missing on `/process` response | The processing run failed before the analyzer completed or a legacy client requested JSON mode before updating. | Verify the job succeeded and that you are on the refreshed branch. JSON mode encodes the same data under `analysis.dieline_layers`. |

## 5. Related Components

- `app/utils/spot_color_renamer.py` – Recursively normalises spot colour tokens and layer names.
- `app/utils/pymupdf_compound_path_tool.py` – Consolidates streams and enforces geometry/styling.
- `tests/test_api_dieline_layers.py` – Regression coverage for schema and header behaviour.
- `README.md` – High-level overview with curl examples and CLI commands.
