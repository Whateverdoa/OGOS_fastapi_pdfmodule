## Batch ZIP Processing and Metadata JSON Validation - Specification

### Goal
Support uploading a ZIP archive containing design PDFs and per-file metadata JSONs. For each PDF, validate and use its sibling metadata JSON to drive processing, return processed PDFs, and preserve the JSON untouched in the results. Provide deterministic outputs and a summary for operational visibility.

### Endpoint
- Method: POST
- Path: `/api/pdf/process-zip`
- Auth: none (for now)
- Request: multipart/form-data
  - `zip_file`: required, `.zip`
  - `return_json`: optional, boolean (default `false`)
    - `false`: returns a ZIP file (`application/zip`)
    - `true`: returns JSON with base64-encoded ZIP

### ZIP Content Contract
- Allowed entries:
  - PDF documents: `*.pdf`
  - Metadata JSON: `*.json` (same basename as its corresponding PDF)
  - Optional subfolders permitted.
- Disallowed entries:
  - Executables, archives within archive, absolute/parent paths (ZipSlip), any non-PDF/JSON payloads used for processing.
- Matching rule:
  - `design.pdf` uses metadata from `design.json` when present in the same folder.

### Metadata JSON Format (per file)
Minimal fields we consume (case-insensitive, both TitleCase and lowercase accepted):
- `ReferenceAtCustomer` | `reference`: string (required if present; default to PDF basename if missing)
- `Description` | `description`: string (optional)
- `Shape` | `shape`: string enum: `circle`, `rectangle`, `custom` (optional, default `custom`)
- `Width` | `width`: number (mm) (optional, default 0)
- `Height` | `height`: number (mm) (optional, default 0)
- `Radius` | `radius`: number (mm) (optional, default 0)
- `Winding` | `winding`: number or string (optional)
- `Substrate` | `substrate`: string (optional)
- `Adhesive` | `adhesive`: string (optional)
- `Colors` | `colors`: string (optional)

Validation rules:
- Types are coerced where sensible: numeric strings → floats/ints; unknown strings kept as-is for pass-through.
- Unknown fields are ignored (but preserved in untouched JSON copy).
- If `Shape` not provided or invalid, use `custom`.
- If JSON is malformed, skip using it (log error) and fall back to default `custom` config derived from PDF basename as `reference` and zeros for dimensions.

### Processing Behavior
1. Safe extract ZIP to temp directory with ZipSlip protection.
2. Discover PDFs recursively via `**/*.pdf` (search all nested folders).
3. For each PDF:
   - Skip jobsheets: if basename contains `jobsheet` (case-insensitive), record `success=skipped` and `message="jobsheet excluded"` in summary; do not process or emit a `.processed.pdf`.
   - Only process design/artwork PDFs: if basename contains `design` or `artwork` (case-insensitive).
   - Find sibling JSON using matching algorithm:
     1. Exact sibling match: `<pdf_stem>.json` in same folder
     2. Order-prefix match: JSON whose stem starts with PDF's order prefix (e.g., `6001681555-3_design_1.pdf` → `6001681555-3_1.json`)
     3. Single JSON in folder: if exactly one JSON exists in PDF's folder, use it
   - If no sibling JSON found, skip and record `success=skipped` and `message="missing sibling json"`.
   - If sibling JSON found, normalize numeric strings (comma to dot: "40,0" → "40.0") and map to `PDFJobConfig`.
   - Call `PDFProcessor.process_pdf(input_path, job_config)` directly (equivalent to single-file endpoint behavior).
   - On success, copy output to results as `<original>.processed.pdf`.
   - Copy sibling JSON to results directory as `<original>.json` (byte-for-byte).
   - Capture analysis-derived headers (e.g., winding route, layer mismatch) into summary.

### Outputs & Naming
- Results saved to `zip_output/<zip_basename>_processed/` directory.
- Processed PDFs named with postfix `.processed.pdf`: `design_1.pdf` → `design_1.processed.pdf`.
- Design/artwork PDFs only; jobsheets are excluded from processing.

- If `return_json=false` (default):
  - Response: `application/zip`, filename `<zip_basename>_processed.zip`.
  - Contents of results ZIP:
    - Processed PDFs: `<original>.processed.pdf` (design/artwork only)
    - Sibling JSONs: `<original>.json` (byte-for-byte copy of JSON used)
    - `summary.csv` with columns:
      - `filename` (original PDF filename)
      - `reference`
      - `shape`
      - `success` (`true`/`false`/`skipped`)
      - `message` (processor message or skip reason)
      - `winding_route` (if available)
      - `layer_mismatch` (`true`/`false`/empty if unknown)
      - `dieline_segment_count` (if available)

- If `return_json=true`:
  - Response: JSON
  - Fields:
    - `success`: boolean
    - `message`: string
    - `files_processed`: integer
    - `results_zip_base64`: base64 string of `<zip_basename>_processed.zip`

### Error Handling
- ZIP-level errors (invalid file, ZipSlip, no PDFs): HTTP 400
- Per-file processing errors do not stop the batch; they are recorded in `summary.csv` with `success=false` and the message.
- HTTP 500 for unexpected server errors.

### Limits & Security
- Max upload size: `settings.max_file_size` (same as single file, or define a distinct batch max).
- Reject archives with:
  - > `settings.batch_max_files` PDFs, if configured
  - Nested archives or suspicious entries
- Always clean up temp files and directories.

### Examples
PowerShell (Windows):
```
$zip = Get-Item "C:\path\to\batch.zip"
$form = @{ zip_file = $zip }
Invoke-WebRequest -Uri "http://localhost:8081/api/pdf/process-zip" -Method Post -Form $form -OutFile "processed_results.zip"
```

curl (Linux/Mac/WSL):
```
curl -X POST -F "zip_file=@/path/to/batch.zip" \
  -o processed_results.zip \
  http://localhost:8081/api/pdf/process-zip
```

### Notes
- Sibling metadata JSON is treated as authoritative for configuration but is not modified or re-serialized; it is copied byte-for-byte to results alongside the processed PDF.
- Numeric strings with comma decimals (e.g., "40,0") are normalized to dot decimals ("40.0") before parsing.
- Processing calls the PDF processor directly for efficiency (equivalent behavior to single-file endpoint).
- Only design/artwork PDFs are processed; jobsheets and PDFs without sibling JSON are skipped.

