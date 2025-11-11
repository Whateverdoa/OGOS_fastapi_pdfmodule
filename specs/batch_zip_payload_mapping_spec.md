## Batch ZIP: Original JSON Preservation and Module Payload Derivation - Specification

### Goal
For each PDF inside an uploaded ZIP, read its sibling metadata JSON, derive a strict `PDFJobConfig` payload for the processing module, and save both:
- the untouched original JSON
- the derived module payload JSON
in the `batch_result` alongside the processed PDF and `summary.csv`.

### Files and Locations
- Input ZIP may contain nested folders. For each design/artwork `X.pdf`, find sibling JSON using matching algorithm:
  1. Exact sibling match: `X.json` in same folder
  2. Order-prefix match: JSON whose stem starts with PDF's order prefix
  3. Single JSON in folder: if exactly one JSON exists in PDF's folder, use it
- Output results ZIP structure:
  - `X.processed.pdf` (processed output)
  - `X.json` (exact bytes from sibling JSON used)
  - `summary.csv`

### Derivation Rules (Mapping → `PDFJobConfig`)
Accept both TitleCase and lowercase keys; case-insensitive. Unknown fields are ignored in the payload but preserved in `X.json`.

Source fields (any of the aliases on the left):
- `ReferenceAtCustomer` | `reference` → `reference: str`
- `Description` | `description` → `description: Optional[str]`
- `Shape` | `shape` → `shape: enum("circle", "rectangle", "custom")`
- `Width` | `width` → `width: float` (mm)
- `Height` | `height` → `height: float` (mm)
- `Radius` | `radius` → `radius: float` (mm)
- `Winding` | `winding` → `winding: Optional[int] | Optional[str]` (coerced to int when possible)
- `Substrate` | `substrate` → `substrate: Optional[str]`
- `Adhesive` | `adhesive` → `adhesive: Optional[str]`
- `Colors` | `colors` → `colors: Optional[str]`

Normalization:
- `shape` is lowercased; if not provided or invalid ⇒ `custom`.
- Numeric fields accept comma or dot decimals. Strings like `"40,0"` are normalized to `"40.0"` before parsing.
- `width`, `height`, `radius` are coerced to float if parseable; else default to `0.0` (after normalization).
- `winding` accepts integers or numeric strings; when possible it's coerced to int, otherwise kept as the original string in payload so it can be logged (it may not map to a route).
- `reference` defaults to the PDF basename if missing/empty.

Validation Policy (default):
- For `rectangle`/`circle` shapes: `width` and `height` should be > 0.0.
  - If missing/invalid, we still produce a payload with zeros and processing will proceed, but the resulting dieline may be degenerate. This is logged in `summary.csv` via `message`.
- For `custom`: No size required; we do not invent dielines when none exist.

### Derived Payload JSON Shape (Internal)
This is the exact object we instantiate as `PDFJobConfig` (values post-normalization) - used internally for processing:
```
{
  "reference": "<string>",
  "description": "<string|null>",
  "shape": "circle" | "rectangle" | "custom",
  "width": <float>,
  "height": <float>,
  "radius": <float>,
  "spot_color_name": "stans",            // default; module constant
  "line_thickness": 0.5,                  // default (pt), unless we add per-job override later
  "winding": <int|string|null>,
  "substrate": "<string|null>",
  "adhesive": "<string|null>",
  "colors": "<string|null>"
}
```

Notes:
- `spot_color_name` and `line_thickness` are module defaults if not specified elsewhere.
- If we later support per-job overrides, include them here and in mapping rules.

### Result Persistence
For each design/artwork `X.pdf` processed:
- Write processed PDF as `X.processed.pdf`.
- If a sibling JSON existed:
  - Save untouched as `X.json` (byte-for-byte copy).
- Append a row in `summary.csv` with at least:
  - `filename`, `reference`, `shape`, `success`, `message`, `winding_route`, `layer_mismatch`, `dieline_segment_count`.

### Error Handling
- Malformed `X.json`: skip PDF, log error in `summary.csv` message with `success=skipped` and `message="malformed json"`.
- Missing `X.json`: skip PDF, log in `summary.csv` with `success=skipped` and `message="missing sibling json"`.
- Any per-file failure: continue processing other files; mark row with `success=false` and error `message`.

### Examples
Given input `label.pdf` and `label.json`:

`label.json` (original):
```
{
  "ReferenceAtCustomer": "JOB-123",
  "Shape": "rectangle",
  "Width": 50,
  "Height": 30,
  "Radius": 2,
  "Winding": "3",
  "Colors": "4"
}
```

`label.payload.json` (derived - internal only):
```
{
  "reference": "JOB-123",
  "description": null,
  "shape": "rectangle",
  "width": 50.0,
  "height": 30.0,
  "radius": 2.0,
  "spot_color_name": "stans",
  "line_thickness": 0.5,
  "winding": 3,
  "substrate": null,
  "adhesive": null,
  "colors": "4"
}
```

### Open Questions (to confirm before hard-enforcing)
- Should `rectangle`/`circle` with zero width/height be rejected (HTTP 400) instead of tolerated?
- Do we want to allow per-job overrides for `spot_color_name` and `line_thickness` via JSON?
- Any additional metadata we should mirror into `summary.csv`?

