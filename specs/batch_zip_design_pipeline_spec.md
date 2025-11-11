## ZIP Design Processing Pipeline - Spec

### Goal
Process only design label PDFs from a ZIP by pairing each with its sibling metadata JSON and sending both to the existing single-file API. Save the processed PDFs together with the original JSON into a new folder named `<zip_basename>_processed`, and provide a zipped bundle as output.

### Inputs
- Endpoint: `POST /api/pdf/process-zip`
- Request: multipart/form-data with `zip_file` (.zip)

### Discovery Rules
- Extract to a temp folder with ZipSlip protection.
- Identify "design label" PDFs:
  - A PDF is considered a design PDF if its basename contains `design` (case-insensitive) AND does not contain `jobsheet`.
- Sibling JSON:
  - For each `X.pdf`, look for `X.json` in the same folder.
  - If not found, SKIP this PDF (do not fall back to order-level JSON).

### Processing Flow
For each matched pair (`X.pdf`, `X.json`):
1. Call `POST /api/pdf/process-with-json-file` with fields:
   - `pdf_file`: the design PDF
   - `json_file`: the sibling JSON
2. Receive processed PDF (file response).
3. Save outputs under a new folder in the host project: `zip_output/<zip_basename>_processed/`:
   - Processed PDF saved as `<X>.processed.pdf`
   - Original sibling JSON saved as `<X>.json` (byte-for-byte)
4. Append row to `summary.csv`:
   - `filename` (X.pdf), `success`, `message` (if available)

Non-design PDFs and jobsheets:
- If basename contains `jobsheet` (case-insensitive), skip and record in summary with `success=skipped` and `message="jobsheet excluded"`.
- All other PDFs without a matching sibling JSON are skipped and recorded as `success=skipped` with `message="missing sibling json"`.

### Output Packaging
- Create `zip_output/<zip_basename>_processed.zip` containing:
  - All processed PDFs `<X>.processed.pdf`
  - Their sibling JSONs `<X>.json`
  - A `summary.csv`
- Response: return the ZIP as `application/zip` (and optionally base64 if `return_json=true`).

### Notes
- This pipeline deliberately avoids using order-level JSON; only per-file sibling JSON is honored.
- Existing validation and normalization occur within the single-file endpoint.

