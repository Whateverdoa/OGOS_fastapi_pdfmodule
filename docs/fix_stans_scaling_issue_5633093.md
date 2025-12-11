# Fix: Stans Dimension Scaling Issue (Job 5633093-8858525)

## Problem

Job 5633093-8858525 was generating a stans (dieline) that was smaller than expected:
- **Expected**: 40mm x 48mm (matching the PDF trimbox)
- **Actual**: 34.90mm x 41.88mm (~12.7% smaller)
- **PDF Trimbox**: 40.00mm x 48.00mm ✓ (correct)
- **PDF Mediabox**: 54.82mm x 62.82mm

## Root Cause

The issue was caused by a mismatch between the overlay PDF canvas size and the base PDF mediabox size during the merge operation:

1. **Shape Generator**: Created overlay PDFs with canvas size based on trimbox dimensions plus offsets
   - Canvas size: `(trimbox_width + 2*trimbox_x0, trimbox_height + 2*trimbox_y0)`
   - This should theoretically match the mediabox, but there was a scaling issue during merge

2. **PDF Merge**: Used `base_page.rect` (which is the mediabox) to place the overlay
   - PyMuPDF's `show_pdf_page()` scales the overlay PDF to fit the placement rectangle
   - The overlay PDF's mediabox didn't exactly match the base PDF's mediabox, causing the entire overlay (including the stans shape) to be scaled down proportionally
   - Even though the trimbox was correct (40x48), the stans ended up smaller due to this scaling

## Solution

Modified the shape generator to create overlay PDFs with the same mediabox size as the base PDF:

1. **Updated `create_circle_dieline()` and `create_rectangle_dieline()`**:
   - Added optional `mediabox_coords` parameter
   - When provided, uses mediabox dimensions for canvas size instead of trimbox-based calculation
   - This ensures the overlay PDF matches the base PDF's mediabox size

2. **Updated `_process_standard_shape()` in PDFProcessor**:
   - Extracts mediabox coordinates from analysis
   - Passes mediabox coordinates to shape generator methods

3. **Updated `merge_pdfs()` in PDFUtils**:
   - Explicitly uses `base_page.mediabox` for placement (was already using it via `base_page.rect`, but now more explicit)

## Files Changed

- `app/core/pdf_processor.py`: Pass mediabox coords to shape generator
- `app/core/shape_generators.py`: Use mediabox for canvas size when provided
- `app/utils/pdf_utils.py`: Explicitly use mediabox for merge placement

## Verification

After the fix:
- Stans dimensions: **40.00mm x 48.00mm** ✓ (matches expected dimensions)

## Impact

This fix ensures that standard shapes (circles and rectangles) are generated at the correct size, matching the job configuration dimensions exactly, regardless of trimbox/mediabox differences in the source PDF.

