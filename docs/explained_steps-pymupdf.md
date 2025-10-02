# PyMuPDF PDF Dieline Processing Guide


This document outlines the step-by-step process for processing PDF dielines using PyMuPDF, with references to the relevant PyMuPDF documentation for each step.

## Overview

The process involves extracting vector drawings (dielines), normalizing them to compound paths with CMYK 100% magenta at 0.5pt stroke width, and optionally managing layers and content streams.

## 1. Extracting Vector Drawings (Dielines)

Use `Page.get_drawings()` or the faster `Page.get_cdrawings()` to retrieve all vector paths from a page. Each path contains items (l, c, re, ...), width, color, and fill properties, allowing you to identify stroke-only lines (typical for dielines).

**Reference:** [PyMuPDF Documentation](https://pymupdf.readthedocs.io)

```python
import pymupdf as fitz

ALIAS = {s.lower() for s in ["KissCut", "Dieline", "DieLine", "CutContour", "Stans", "stans"]}

def extract_stroke_paths(page):
    """Extract stroke-only paths from a page (faster alternative: page.get_cdrawings())"""
    paths = page.get_drawings()  
    stroke_only = [
        p for p in paths
        if p.get("fill") in (None, []) and p.get("width", 0) > 0
    ]
    return stroke_only
```

**Note:** `get_drawings()` returns colors as RGB tuples (by design) – spot/Separation names are not visible here. Therefore, we don't filter by name but by stroke-only + geometry, and apply the desired style when redrawing.

## 2. Creating Compound Paths with CMYK 100% Magenta, 0.5pt

Using the Shape API, you can draw multiple sub-paths and close them with a single `finish()` call, effectively creating one "compound" drawing. CMYK values can be passed as 4-tuples (0..1).

**Reference:** [PyMuPDF Shape API](https://pymupdf.readthedocs.io)

```python
MAGENTA_CMYK = (0.0, 1.0, 0.0, 0.0)  # 100% Magenta
LINE_WIDTH_PT = 0.5

def redraw_as_compound(page, paths, overlay=True):
    """Redraw multiple paths as a single compound path"""
    shape = page.new_shape()
    for p in paths:
        for item in p["items"]:
            op = item[0]
            if op == "l":      
                shape.draw_line(item[1], item[2])
            elif op == "re":   
                shape.draw_rect(item[1])
            elif op == "qu":   
                shape.draw_quad(item[1])
            elif op == "c":    
                shape.draw_bezier(item[1], item[2], item[3], item[4])
            else:
                # Add other operators as needed
                pass
    
    # Single finish() -> one compound vector object
    shape.finish(
        color=MAGENTA_CMYK,  # stroke CMYK
        fill=None,
        width=LINE_WIDTH_PT,
        closePath=True
    )
    shape.commit(overlay=overlay)  # place in foreground
```

**Why this works:** The Drawing recipe shows exactly this pattern: `get_drawings()` → redraw all items → single `finish()` → `commit()`. This allows you to group paths into one composite shape without changing coordinates.

## 3. Replacing Regular Shapes (Rectangle/Circle/Oval)

For known shapes, you can remove the existing dieline and draw a clean shape:

**Removal:** The official recipe recommends using redaction to remove vector drawings by bounding box.
**Replacement:** Draw with `draw_rect()` or `draw_oval()`/`draw_circle()` and commit with CMYK magenta + 0.5pt.

**Reference:** [PyMuPDF Redaction](https://pymupdf.readthedocs.io)

```python
def replace_regular_with_box(page, bbox):
    """Replace existing drawing in bbox with a clean rectangle"""
    # 1) Delete existing drawing in this area
    page.add_redact_annot(bbox)
    page.apply_redactions(images=0, drawings=2, text=1)  # remove drawings in bbox
    
    # 2) Draw new dieline (rectangle)
    shp = page.new_shape()
    shp.draw_rect(bbox)
    shp.finish(color=MAGENTA_CMYK, fill=None, width=LINE_WIDTH_PT, closePath=True)
    shp.commit(overlay=True)

def replace_regular_with_circle(page, center, radius):
    """Replace with a clean circle"""
    shp = page.new_shape()
    shp.draw_circle(center, radius)
    shp.finish(color=MAGENTA_CMYK, fill=None, width=LINE_WIDTH_PT)
    shp.commit(overlay=True)
```

The "Delete Drawings" section shows how to remove vector objects in an area using redact annotations.

## 4. Preserving Custom/Irregular Shapes with Normalization

For custom shapes: don't remove, but redraw as compound (step 2). If there are multiple dielines (inner-outer), pass all relevant paths to `redraw_as_compound()` — this gives you one compound path without geometry shifting. (All coordinates come 1:1 from `get_drawings()`.)

```python
def normalize_custom(page):
    """Normalize custom shapes as compound paths"""
    dieline_paths = extract_stroke_paths(page)
    if not dieline_paths:
        return
    
    # Redraw as one compound, keep original or remove afterwards if desired
    redraw_as_compound(page, dieline_paths, overlay=True)
    
    # Optional: remove old vectors within their bounding boxes
    # for p in dieline_paths:
    #     page.add_redact_annot(p["rect"])
    # page.apply_redactions(images=0, drawings=2, text=0)
```

## 5. (Optional) Assigning OCG Layer "stans"

PyMuPDF supports Optional Content Groups (layers). You can create an OCG and link objects to it via `Document.add_ocg()` and `Document.set_oc(xref, ocg_xref)` — straightforward for images/annotations. For vector content written as content-stream (like Shape drawings), the API has no direct `oc=` parameter, but OCGs are fully supported in general.

**Reference:** [PyMuPDF OCG Documentation](https://pymupdf.readthedocs.io)

```python
def ensure_ocg(doc, name="stans"):
    """Create (or reuse) an OCG, returns xref"""
    ocg_xref = doc.add_ocg(name)  # creates default OC-config if needed
    return ocg_xref
```

**Limitation (PyMuPDF):** For content created by `Shape.commit()`, there's no documented high-level way to attach those paths to an OCG — `oc=` exists for operations like `insert_image`. OCGs are otherwise fully manageable (create, assign to objects with xref).

## 6. (Advanced) Renaming Tokens in Content Streams to "stans"

If you also want to replace all old names (/KissCut, /Dieline, ...) with /stans in the raw PDF content, you can do this with the low-level API: get the /Contents xrefs of the page, read bytes with `Document.xref_stream()`, do a safe string-replace, and write back with `Document.update_stream()`. This is exactly how the low-level recipes recommend it.

**Reference:** [PyMuPDF Low-Level Interfaces](https://pymupdf.readthedocs.io)

```python
def rename_tokens_in_streams(doc, page):
    """Rename dieline tokens in content streams to 'stans'"""
    xrefs = page.get_contents()  # list of content-stream xrefs
    if not xrefs:
        return
    
    for xr in xrefs:
        src = doc.xref_stream(xr)  # bytes (decompressed)
        # Case-insensitive replacement of known alias names to 'stans'
        for alias in ALIAS:
            src = src.replace(f"/{alias}".encode("latin-1"), b"/stans")
        doc.update_stream(xr, src)  # compresses back if useful
```

The Low-Level Interfaces recipe shows how to read/write streams; `Page.get_contents()` retrieves the involved xrefs.

## 7. Overprint Support

**Render Support:** MuPDF/PyMuPDF supports overprint rendering (display). This is visible in `TOOLS.fitz_config['plotter-n'] == True`.

**Setting on Paths:** The documentation doesn't offer a documented high-level setter to toggle "Overprint Stroke" on an individual vector path. (Annotations have color/opacity; shapes have stroke_opacity, width, etc., but no overprint toggle.) You can set CMYK and all line styles as done above.

**Practical Advice:** In many RIP flows, a Spot/Separation + overprint simulation suffices. PyMuPDF doesn't expose an API to create a named Separation spot or place overprint operators; that requires manual content-stream injection (PDF operators /ExtGState). The docs don't cover this as high-level API.

## 8. Complete End-to-End Example

```python
import pymupdf as fitz

def process_pdf(in_path, out_path, shape_kind="custom"):
    """Process PDF with dieline normalization"""
    doc = fitz.open(in_path)

    for page in doc:
        # 1) Extract vector paths
        stroke_paths = extract_stroke_paths(page)

        if shape_kind in ("rect", "square", "circle", "oval"):
            # Regular: remove + replace
            # Here you would determine bbox (e.g., largest stroke path)
            if stroke_paths:
                bbox = stroke_paths[0]["rect"]
                if shape_kind in ("rect", "square"):
                    replace_regular_with_box(page, bbox)
                else:
                    # Simple heuristic: circle within bbox
                    center = bbox.tl + (bbox.width/2, bbox.height/2)
                    radius = min(bbox.width, bbox.height)/2
                    # Remove first if needed:
                    page.add_redact_annot(bbox)
                    page.apply_redactions(images=0, drawings=2, text=0)
                    replace_regular_with_circle(page, center, radius)
        else:
            # Custom/irregular: compound path with magenta 0.5pt
            if stroke_paths:
                # Redraw as one compound path
                redraw_as_compound(page, stroke_paths, overlay=True)
                # Optional: remove old vectors
                for p in stroke_paths:
                    page.add_redact_annot(p["rect"])
                page.apply_redactions(images=0, drawings=2, text=0)

        # 2) (Optional) Rename all known name-tokens to /stans
        rename_tokens_in_streams(doc, page)

    doc.save(out_path, deflate=True)  # Standard save; deflate compresses
```

## References

- **Shapes & Colors:** CMYK / line width via `Shape.finish()` / `commit()` ([Shape API](https://pymupdf.readthedocs.io))
- **Compound Paths:** Multiple sub-paths before one `finish()` → one composite path ([Shape API](https://pymupdf.readthedocs.io))
- **Removal:** Via redact recipe ([Redaction](https://pymupdf.readthedocs.io))
- **Stream Renaming:** Via low-level functions ([Low-Level Interfaces](https://pymupdf.readthedocs.io))
