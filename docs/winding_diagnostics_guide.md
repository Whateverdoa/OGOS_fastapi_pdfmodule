# Winding Diagnostics Guide

## Overview

This guide explains how to diagnose winding value issues in the PDF processing pipeline. The system includes diagnostic tools to trace winding values from input through processing to output.

## Understanding the Winding Flow

### Winding-to-Rotation Mapping

The PDF module maps winding values to rotation angles:

- **Winding 2** → 0° rotation (no dimension swap)
- **Winding 3** → 90° rotation (dimensions swapped downstream)
- **Winding 4** → 270° rotation (dimensions swapped downstream)
- **Winding 1** → 180° rotation
- **Windings 5-8** → Inverted equivalents

### Processing Flow

1. **Input**: Converter program sends JSON with `Winding` value (passed through unchanged)
2. **Processing**: PDF module:
   - Maps winding to rotation angle
   - Applies rotation to PDF artwork
   - **Keeps original winding value** in output JSON (upstream system handles rotation)
   - **Does NOT swap dimensions** - this happens downstream
3. **Output**: JSON with original `Winding` value and original dimensions
4. **Downstream**: `pdf_validator_client.py` swaps dimensions if rotation is 90° or 270°

## Diagnostic Tools

### 1. API Endpoint: `/api/pdf/diagnose-winding/{order_reference}`

Diagnostic endpoint to trace winding values for a specific order.

**Example Request:**
```bash
curl http://localhost:8000/api/pdf/diagnose-winding/6001949316-2
```

**Response includes:**
- Files found (original PDFs, processed PDFs, JSON configs)
- Winding flow analysis showing:
  - Input winding value and type
  - Calculated rotation angle
  - Whether dimensions should be swapped downstream
  - Normalized output winding value
  - Any errors encountered

### 2. CLI Tool: `diagnose_order.py`

Command-line tool for diagnosing orders locally.

**Usage:**
```bash
python diagnose_order.py 6001949316-2
python diagnose_order.py 6001949316-2 --verbose
```

**Output includes:**
- Files found in storage directories
- Winding flow analysis
- Dimension expectations
- Error messages

### 3. Enhanced Response Headers

All PDF processing endpoints now include additional headers:

- `X-Winding-Value`: The winding value received
- `X-Rotation-Angle`: Calculated rotation angle (0, 90, 180, 270)
- `X-Needs-Rotation`: Whether rotation was applied
- `X-Should-Swap-Dimensions`: Whether dimensions should be swapped downstream
- `X-Winding-Error`: Error message if winding value is invalid

## Common Issues and Solutions

### Issue: Winding=4 but should be 2

**Symptoms:**
- Output JSON shows `Winding: 4` instead of `2`
- Dimensions not swapped (110×15 instead of 15×110)

**Diagnosis Steps:**

1. **Check input source:**
   ```bash
   python diagnose_order.py 6001949316-2
   ```
   Look at the "INPUT" section to see what winding value was received.

2. **Verify converter output:**
   - The converter program passes through winding values unchanged
   - Check the OGOS system that generates the original JSON
   - The issue is likely upstream where winding is set incorrectly

3. **Check processing status:**
   - If file is in `processed-failed/`, PDF module didn't run successfully
   - This explains why dimensions weren't swapped

### Issue: Dimensions not swapped when they should be

**Symptoms:**
- Winding=3 or Winding=4 (should trigger swap)
- Dimensions remain unchanged (e.g., 110×15 instead of 15×110)

**Diagnosis Steps:**

1. **Check rotation calculation:**
   ```bash
   curl http://localhost:8000/api/pdf/route-by-winding/4
   ```
   Should return `{"winding_value": "4", "route": 270}`

2. **Verify downstream processing:**
   - Check `pdf_validator_client.py` logs
   - Dimension swap happens AFTER this PDF module
   - This module only rotates the PDF, doesn't swap dimensions

3. **Check response headers:**
   - Look for `X-Should-Swap-Dimensions: true` in API response
   - If missing, winding value may not have been recognized

## Where to Check

### 1. Source of Winding Value

The converter program (`src/json_processor.py` line 474) passes through winding unchanged:
```python
winding=order.winding,  # Simply passed through, never modified
```

**Action:** Check the OGOS system that generates the original order JSON.

### 2. PDF Processing Status

**Check storage directories:**
- `pdf_storage/original/` - Original uploaded files
- `pdf_storage/processed/` - Successfully processed files
- `pdf_storage/processed-failed/` - Failed processing attempts

**Action:** If file is in `processed-failed/`, investigate why processing failed.

### 3. Downstream Dimension Swap

Dimension swapping happens in `pdf_validator_client.py` (lines 257-263):
- If rotation is 90° or 270°, width and height are swapped
- This happens AFTER the OGOS PDF module processes the file

**Action:** Check logs from the validator client to see if swap occurred.

## Example Diagnostic Output

```
Diagnosing order: 6001949316-2

============================================================
FILES FOUND
============================================================

Original Files (1):
  - 20251208_114402_6001949316-2_design_1.pdf (12345 bytes)

Processed Files (1):
  - 20251208_114402_6001949316-2_design_1_processed_6001949316-2.pdf (12345 bytes)

JSON Files (1):
  - config.json
    Winding: 4
    Dimensions: 110.0 × 15.0

============================================================
WINDING FLOW ANALYSIS
============================================================

📄 config.json
============================================================
INPUT
============================================================
  Winding: 4 (type: int)
  Width: 110.0
  Height: 15.0

============================================================
PROCESSING
============================================================
  Parsed Winding: 4
  Rotation Angle: 270°
  Needs Rotation: True
  Should Swap Dimensions: True

============================================================
OUTPUT
============================================================
  Normalized Winding: 2
  ⚠️  Winding was changed during normalization

============================================================
DIMENSIONS
============================================================
  Input: 110.0 × 15.0
  ⚠️  Expected downstream swap: 15.0 × 110.0
```

## API Integration

The diagnostic endpoint can be integrated into monitoring or debugging workflows:

```python
import requests

def check_order_winding(order_ref: str):
    response = requests.get(
        f"http://localhost:8000/api/pdf/diagnose-winding/{order_ref}"
    )
    data = response.json()
    
    # Check for issues
    for json_name, analysis in data["analysis"].items():
        if analysis.get("errors"):
            print(f"Issues in {json_name}: {analysis['errors']}")
        
        # Check if dimensions should be swapped
        if analysis.get("dimensions", {}).get("expected_downstream_swap"):
            print("⚠️ Dimensions should be swapped downstream")
```

## Related Documentation

- `docs/winding_routing_specification.md` - Winding routing specification
- `specs/reseller_processing_spec.md` - Reseller processing rules
- `specs/spec_smart_dimension_swapping.md` - Smart dimension swapping logic

