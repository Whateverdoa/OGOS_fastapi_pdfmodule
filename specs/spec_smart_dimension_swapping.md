# Smart Dimension Swapping & Reseller Detection Spec

## ID
SPEC-00X (Draft)

## Status
Implemented

## Context
A production issue occurred with Order 5623221-8841620 where:
1.  **Reseller Detection Failed**: The file was renamed to ` .PDF`, bypassing filename-based detection. This caused the system to skip the "Reseller Logic" (which handles `Winding` rotation and dimension swapping).
2.  **Orientation Mismatch**: The job configuration specified `48x70` (Vertical), but the artwork was `70x48` (Horizontal). Since `Winding=2` implies 0° rotation, no automatic rotation or dimension swap occurred, leading to incorrect stans generation (vertical oval on horizontal page).

## Features Implemented

### 1. Robust Reseller Detection
**Problem**: Heuristic relied solely on filenames or specific keywords ("Print.com") which failed with malformed filenames.
**Solution**: 
- If the JSON configuration contains the key `Winding` (case-insensitive), the order is **forcefully detected as a Reseller order**.
- **Impact**: Ensures that rotation logic (0°, 90°, 180°, 270°) and standard dimension swapping (for 90°/270°) are always considered for these orders, regardless of the filename.

### 2. Smart Dimension Swapping
**Problem**: Even with reseller detection, Winding 2 (0°) does not trigger a rotation. If the metadata orientation differs from the file orientation, the stans (dieline) is generated with the wrong aspect ratio.
**Logic**:
- **Trigger**: Implemented in `PDFProcessor` after PDF Analysis.
- **Condition**: 
    - Let `ConfigW`, `ConfigH` be the job configuration dimensions.
    - Let `PdfW`, `PdfH` be the actual PDF Trimbox dimensions.
    - Match is found if `|ConfigW - PdfH| < 1mm` AND `|ConfigH - PdfW| < 1mm`.
- **Action**: If a transposed match is found, `ConfigW` and `ConfigH` are **swapped** in the configuration object.
- **Rationale**: The artwork's physical dimensions are considered the "source of truth" for orientation when dimensions match transitively.

## Technical Details

### Location
- **Reseller Detection**: `app/api/endpoints/pdf.py` -> `_detect_reseller`
- **Dimension Swapping**: `app/core/pdf_processor.py` -> `process_pdf`

### Pseudocode (Smart Swapping)
```python
if not direct_match(Config, PDF):
    if transposed_match(Config, PDF):
        Config.swap_dimensions()
        Log("Swapped dimensions to match PDF orientation")
```
