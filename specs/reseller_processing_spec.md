## Reseller Processing: Rotation, Winding Normalization, and Trimbox Validation

### Purpose
Define the behavior for reseller orders to normalize artwork orientation and winding, and specify how trimbox dimensions are validated against provided configuration/JSON.

### Reseller Detection
- A job is considered a reseller job if any of the following contain one of these keywords (case-insensitive): `print.com`, `helloprint`, `drukwerkdeal`, `cimpress`.
  - ZIP/folder/file names
  - JSON fields: `Customer`, `Reseller`, `Client`, `Brand`, `Company`, `Supplier`, `SupplierId` (and lowercase variants)

### Endpoints Affected
- `POST /api/pdf/process-zip`
- `POST /api/pdf/process-with-json-file`

Both endpoints share the following behavior.

### Rotation and Winding Rules (Reseller Jobs)
- Input JSON may include explicit rotation via any of: `Rotate`, `rotate`, `Orientation`. Valid values: 0, 90, 180, 270.
  - If provided, the explicit rotation is applied.
- If no explicit rotation is provided AND a winding value exists, we derive rotation from winding using the routing table:
  - Winding → Rotation: `1→180`, `2→0`, `3→90`, `4→270`, `5→0`, `6→0`, `7→0`, `8→0`.
- When reseller keywords (print.com, helloprint, drukwerkdeal) are detected, apply the winding-derived rotation when no explicit rotation exists; when the resulting rotation is 90 or 270 degrees, swap the normalized `width`/`height` before forcing the JSON `winding` value to 2.
- Rotation is applied to every page of the PDF before any analysis or dieline generation.

Single-file endpoint notes:
- The same reseller rules apply when posting a single PDF + JSON. Rotation is applied and `winding` is normalized to 2 internally for processing.

### Non-Reseller Jobs
- No automatic rotation is applied unless the JSON explicitly provides `Rotate`/`rotate`/`Orientation`.
- Winding is not modified.

### Numeric Normalization
- Numeric strings with comma decimals are normalized (e.g., `"40,0" → 40.0`) before parsing.

### Results JSON Persistence
- Batch ZIP results persist a single JSON per source configuration (named after the original JSON file) alongside all processed PDFs:
  - Reseller jobs: the JSON saved in results is the normalized version (forced `Winding=2`; `Rotate` set when rotation was derived from winding and not explicitly provided, with dimensions swapped when a perpendicular rotation is applied).
  - Non-reseller jobs: the JSON saved in results is the original uploaded JSON (unchanged).
- Additional processed PDFs that reuse the same configuration do not emit duplicate JSON copies.

### Trimbox vs Config Validation
- Definitions:
  - Trimbox: Page box detected from the PDF analysis (in millimeters).
  - Config dimensions: `width`, `height` from JSON after normalization.
- Validation:
  - Compare `trimbox_width` × `trimbox_height` with `config.width` × `config.height` after accounting for applied rotation (swap width/height when rotated by 90 or 270 degrees).
  - Tolerance: `±1.0 mm` per dimension.
- Mismatch Handling (current policy):
  - We do not modify the provided `width`/`height`.
  - We record the outcome in summary:
    - `trimbox_width`, `trimbox_height` (mm)
    - `config_width`, `config_height` (mm)
    - `trimbox_mismatch` = `true` when either dimension differs by more than 1.0 mm; `false` otherwise
  - Processing continues using the configured dimensions.
- Future option (not enabled by default):
  - `auto_correct_dimensions=true` could adjust `width`/`height` to match the trimbox when a mismatch is detected.

### Summary Output Additions (batch ZIP)
- Columns added:
  - `reseller_detected`: `true`/`false`
  - `applied_rotation`: `0|90|180|270` (empty if none)
  - `trimbox_width`, `trimbox_height`
  - `config_width`, `config_height`
  - `trimbox_mismatch`: `true`/`false`

### Rationale
- Reseller platforms often require a canonical winding/orientation for production; normalizing to winding 2 ensures consistent finishing.
- Logging trimbox vs config provides visibility into potential specification issues without blocking throughput.


