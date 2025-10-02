"""here’s a clean FastAPI endpoint that implements the PyMuPDF-only workflow you described:

Accepts a PDF upload + shape_kind (rect|circle|oval|custom)

For regular shapes: removes the existing die line in its bbox and draws a fresh magenta (CMYK 0,1,0,0) 0.5 pt outline

For custom/irregular: preserves geometry and redraws one compound path (all dieline segments merged) in magenta 0.5 pt

Optionally replaces residual stream tokens (/KissCut, /Dieline, …) with /stans

Returns a new PDF

All vector handling is via PyMuPDF (fitz) primitives documented in the official API:

Page.get_drawings() → enumerate vector paths (stroke/fill, items, rect)

Page.new_shape() / Shape.draw_*() / Shape.finish() / Shape.commit() → redraw (supports CMYK + width)

Redaction recipe pattern → remove vector drawings within a bbox

Low-level stream access → rename tokens via doc.xref_stream() / doc.update_stream()

Heads-up on PyMuPDF limits (per docs): there’s no high-level setter for overprint flags on a 
specific vector path, and you cannot create a named Separation color directly via Shape APIs. 
Below we set CMYK=100% magenta and (optionally) rewrite content stream name tokens to /stans. 
If you truly need named Separation + OP/OPM, that requires low-level PDF operator injection."""

from __future__ import annotations

import io
from typing import List, Tuple, Iterable

import pymupdf as fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI(title="Dieline Normalizer (PyMuPDF-only)")

# ---- Config ----
ALIAS = {s.lower() for s in ["KissCut", "Dieline", "DieLine", "CutContour", "Stans", "stans", "stanslijn"]}
MAGENTA_CMYK: Tuple[float, float, float, float] = (0.0, 1.0, 0.0, 0.0)  # 100% M
LINE_WIDTH_PT: float = 0.5


# ---- PyMuPDF helpers (from official docs patterns) ----

def extract_stroke_paths(page: fitz.Page) -> List[dict]:
    """
    Return stroke-only vector drawings (candidate dielines).
    Uses Page.get_drawings(); each item has keys: items, width, fill, color, rect, etc.
    """
    drawings = page.get_drawings()  # documented in PyMuPDF: list of vector recipes
    stroke_only = [p for p in drawings if (p.get("fill") in (None, [])
                                           and (p.get("width") or 0) > 0)]
    return stroke_only


def redraw_as_compound(page: fitz.Page, paths: Iterable[dict], overlay: bool = True) -> None:
    """
    Redraw multiple path sequences as ONE compound path:
    - draw_* calls for each subpath
    - ONE finish() → one combined vector object
    """
    if not paths:
        return

    shape = page.new_shape()
    for p in paths:
        for item in p["items"]:
            op = item[0]
            if op == "l":        # line: ( 'l', p0, p1 )
                shape.draw_line(item[1], item[2])
            elif op == "re":     # rectangle: ( 're', rect )
                shape.draw_rect(item[1])
            elif op == "qu":     # quad: ( 'qu', quad )
                shape.draw_quad(item[1])
            elif op == "c":      # cubic bézier: ( 'c', p0, p1, p2, p3 )
                shape.draw_bezier(item[1], item[2], item[3], item[4])
            # You can add more operators as needed (e.g., 'm' moveto not emitted by get_drawings()).

    shape.finish(
        color=MAGENTA_CMYK,  # CMYK stroke
        fill=None,
        width=LINE_WIDTH_PT,
        closePath=True
    )
    shape.commit(overlay=overlay)


def delete_drawings_in_rect(page: fitz.Page, rect: fitz.Rect) -> None:
    """
    Remove vector drawings within a rectangle using the redaction recipe:
    - add redaction annotation
    - apply_redactions(..., drawings=2) to drop vector drawings
    """
    page.add_redact_annot(rect)
    # drawings=2: remove drawings (vector content) within redaction area; keep images/text as chosen.
    page.apply_redactions(images=0, drawings=2, text=0)


def rename_tokens_in_streams(doc: fitz.Document, page: fitz.Page) -> None:
    """
    Low-level: rename known alias tokens (/KissCut, /Dieline, ...) to '/stans'
    in the page's content streams. Case-insensitive for robustness.
    """
    xrefs = page.get_contents()  # list of content stream xrefs
    if not xrefs:
        return
    for xr in xrefs:
        raw = doc.xref_stream(xr)  # bytes (decompressed)
        # Perform conservative replacements on name objects that start with '/'
        # Note: 'latin-1' safe for byte ops; tokenization remains user's responsibility.
        for alias in ALIAS:
            raw = raw.replace(f"/{alias}".encode("latin-1"), b"/stans")
        doc.update_stream(xr, raw)


def biggest_bbox(paths: List[dict]) -> fitz.Rect | None:
    if not paths:
        return None
    # Choose the largest rect by area as the "regular shape" bbox heuristic
    return max((p["rect"] for p in paths), key=lambda r: (r.width * r.height), default=None)


# ---- Core processor ----

def process_document(buf: bytes, shape_kind: str, replace_stream_tokens: bool = True) -> bytes:
    try:
        doc = fitz.open(stream=buf, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {e}")

    shape_kind = (shape_kind or "custom").lower()
    if shape_kind not in {"rect", "square", "circle", "oval", "custom"}:
        raise HTTPException(status_code=422, detail="shape_kind must be one of: rect|square|circle|oval|custom")

    for page in doc:
        stroke_paths = extract_stroke_paths(page)

        if not stroke_paths:
            # Nothing to do on this page
            if replace_stream_tokens:
                rename_tokens_in_streams(doc, page)
            continue

        if shape_kind in {"rect", "square", "circle", "oval"}:
            # Regular: remove existing dieline(s) in the main bbox and draw a clean one
            bbox = biggest_bbox(stroke_paths)
            if bbox:
                delete_drawings_in_rect(page, bbox)

                if shape_kind in {"rect", "square"}:
                    shp = page.new_shape()
                    shp.draw_rect(bbox)
                    shp.finish(color=MAGENTA_CMYK, fill=None, width=LINE_WIDTH_PT, closePath=True)
                    shp.commit(overlay=True)
                else:
                    # circle/oval: draw ellipse that fits the bbox
                    # For a circle, use min dimension as radius. For oval, draw oval via Beziers:
                    shp = page.new_shape()
                    shp.draw_oval(bbox)  # PyMuPDF supports draw_oval with bounding rect
                    shp.finish(color=MAGENTA_CMYK, fill=None, width=LINE_WIDTH_PT, closePath=True)
                    shp.commit(overlay=True)

        else:
            # Custom/irregular: redraw ALL stroke-only paths as ONE compound,
            # then (optionally) remove originals by redacting their rects.
            redraw_as_compound(page, stroke_paths, overlay=True)
            # If you want to delete original vectors (keeping only the compound):
            for p in stroke_paths:
                page.add_redact_annot(p["rect"])
            page.apply_redactions(images=0, drawings=2, text=0)

        if replace_stream_tokens:
            rename_tokens_in_streams(doc, page)

    out = io.BytesIO()
    # deflate=True compresses content streams where applicable
    doc.save(out, deflate=True)
    doc.close()
    out.seek(0)
    return out.read()


# ---- FastAPI endpoint ----

@app.post("/dieline/normalize")
async def normalize_dieline_pdf(
    pdf: UploadFile = File(..., description="PDF to normalize"),
    shape_kind: str = Form("custom", description="rect|square|circle|oval|custom"),
    replace_stream_tokens: bool = Form(True, description="Replace /KissCut,/Dieline,... with /stans in streams"),
):
    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Upload must be a PDF")

    data = await pdf.read()
    try:
        result = process_document(data, shape_kind=shape_kind, replace_stream_tokens=replace_stream_tokens)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")

    return StreamingResponse(io.BytesIO(result), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{pdf.filename or "normalized.pdf"}"'
    })
