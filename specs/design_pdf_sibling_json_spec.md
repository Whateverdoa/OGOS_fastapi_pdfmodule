## Design PDF ↔ Sibling JSON Mapping - Spec

### Purpose
Define the rule to pair a design/artwork PDF with its sibling metadata JSON inside ZIP batches, and describe how processing and outputs should be handled.

### Core Rule
- A design PDF named like:
  - `6001681555-3_design_1.pdf`
- Pairs with the sibling JSON in the same folder whose name represents the order context without the design postfix, e.g.:
  - `6001681555-3_1.json`

- Notes:
- “design” or “artwork” (case-insensitive) identifies artwork PDFs we should verify and process.
- “jobsheet” (case-insensitive) PDFs are excluded from processing.

### Matching Algorithm (per PDF)
Given a PDF file `X.pdf` in folder `F` with stem `X`:
1) Exact sibling match (if present):
   - `F/X.json`
2) Order-number sibling match (preferred fallback):
   - Compute `order_prefix = X.split('_')[0]`
   - In folder `F`, find `*.json` with `stem.startswith(order_prefix)`
   - If multiple candidates, pick the one with the shortest stem (closest match)
3) Folder-level singleton JSON (secondary fallback):
   - If there is exactly one `*.json` in `F`, use it
4) Otherwise → no sibling JSON → skip and record in summary

Examples:
- `6001681555-3_design_1.pdf` → `6001681555-3_1.json` (same folder)
- `ABC-42_design_3.pdf` → `ABC-42_3.json` (same folder)

### Processing Flow (per matched pair)
1) Send the pair to the single-file endpoint:
   - `POST /api/pdf/process-with-json-file`
   - `pdf_file = X.pdf`, `json_file = chosen_json`
2) Receive processed PDF as file response
3) Save results under `zip_output/<zip_basename>_processed/`:
   - `<X>.processed.pdf` (processed output)
   - `<X>.json` (byte-for-byte copy of the sibling JSON used)
4) Append to `summary.csv`:
   - `filename` (X.pdf), `success`, `message` (or reason if skipped)

### Exclusions
- `jobsheet` PDFs are skipped; report in summary with `success=skipped` and `message="jobsheet excluded"`.
- PDFs without a resolvable sibling JSON (per rules above) are skipped; message `"missing sibling json"`.

### Output Packaging
- Write `zip_output/<zip_basename>_processed.zip` containing:
  - All `<X>.processed.pdf` (design PDFs only)
  - All `<X>.json` used for those PDFs
  - `summary.csv`

### Rationale
- Order-number sibling fallback mirrors real-world file drops where the order JSON describes all designs in a folder, and design postfixes indicate variants.
- Restricting to folder-local JSON prevents accidental cross-folder pairing.

