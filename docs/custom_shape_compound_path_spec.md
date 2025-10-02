# Custom Shape Compound Path – PyMuPDF Implementation Plan

## Problem Statement
The current compound-path workflow relies on PyPDF content-stream surgery. Nested form XObjects, graphics-state inheritance, and resource merging make that approach brittle: dieline segments can shift, overprint states go missing, and some `/stans` strokes remain split across multiple paths. PyPDF is a document-assembly library and offers no native API for path editing, so the converter is effectively rewriting PostScript by hand.

We need a geometry-safe solution that:
- Preserves the exact coordinates of every dieline segment.
- Emits a single stroked path in `/stans`, 100 % magenta, overprint-on.
- Leaves other artwork untouched and keeps optional-content layer bindings intact.

## PyMuPDF Rationale
PyMuPDF (MuPDF) exposes high-level vector APIs: `page.get_drawings()` returns individual path objects (including move/line/curve segments), along with stroke colour, fill, width, and optional content information. PyMuPDF can also draw new paths via `fitz.Shape`, allowing us to rebuild the dieline as one compound path while retaining the original coordinates. Unlike PyPDF, MuPDF handles all resource bookkeeping and respects layer/graphics-state settings when we reinsert shapes.

We already vendor PyMuPDF (see `app/core/pdf_analyzer.py`), and the analyzer dump is handy for debugging path geometry. We will leverage that analysis pipeline to validate what’s on the page before rewriting it.

examine the example code : docs\example-code\compound_end_to_end .py and docs\example-code\example_pymupdf_app.py

examin the guide : docs\custom_shape_compound_path_spec.md

## Proposed Workflow
1. **Analyse the Input Page**
   - Use the existing `PDFAnalyzer` (wraps `page.get_drawings()` and resource inspection) to list all drawing items.
   - Identify dieline candidates by spot colour name (`stans`, `kisscut`, etc.), stroke CMYK, or optional-content layer naming.
   - Surface the raw stroke segments (layer, width, bbox) and flag `layer_mismatch` when dieline aliases span multiple layers so the pipeline knows a merge is required.
   - Capture metadata: bounding boxes, path segment lists, associated OCG/OCMD ids, stroke width, and overprint flags.

2. **Collect Target Segments**
   - Walk the drawing list and select any stroke-only path whose colour name or layer matches the dieline mapping.
   - Preserve ordering so we can rebuild the path in the same stacking context (e.g., outer shape first, inner paths second if necessary).
   - Combine segments into a structure that records all move/line/curve commands with absolute coordinates. If segments are disjoint, keep separate subpaths in the compound object (outer stroke + any holes).

3. **Regenerate a Single Compound Path**
   - Use `page.get_cdrawings()` to extract stroke commands from each `/stans` sequence and merge them into one ordered list of PDF path operators (`m`, `l`, `c`, `re`).
   - Preserve wrapping context (optional-content BDC/EMC, graphics states, matrices) taken from the first sequence so the combined path inherits the original layer membership.

4. **Remove Original Segments & Write Back**
   - Locate the relevant Form XObject streams via PyPDF (`/Resources` lookup) and rewrite them in place with PyMuPDF’s `doc.update_stream(xref, data)`.
   - Drop all redundant `/stans` stroke blocks and insert the new combined block immediately after the captured prelude (`/CS` + `SCN` + `w` commands).
   - Save with `doc.save(..., deflate=True)` so the external workflow sees only the compound path.

## Detailed Task List
1. **Add a Drawing Inspector Utility**
   - Extend `PDFAnalyzer` with a helper that filters drawings by colour/layer and exports JSON (coordinates, commands, OCG id). This gives us regression fixtures and makes debugging easier.

2. **Implement `PyMuPDFCompoundBuilder`**
   - New module under `app/utils/compound_builder.py` that encapsulates:
     - `collect_segments(doc, page_index) -> CompoundSegments`
     - `replace_with_compound(doc, page_index, segments, colour_spec)`
   - Accept configuration: target spot names, stroke width, tolerance for joining endpoints (e.g., snap endpoints within 0.01 pt).

3. **Integrate with Existing Pipeline**
   - Ensure the PyMuPDF tool runs for every processed PDF (custom and generated shapes) so multi-layer dielines are merged automatically.
   - Keep the legacy PyPDF renamer in place as a fast pre-pass, then invoke the PyMuPDF stream rewrite and final colour enforcement in `PDFProcessor` for both custom and standard branches.

4. **Testing Strategy (TDD)**
   - Synthetic fixture: generate a PDF with two separate magenta stroked rectangles (outer + hole). Assert the builder outputs one compound path (1 `S` command) and the bounding boxes match.
   - Real fixture: `6001857074-1_design_1.pdf`. Use analyzer dumps to assert that:
     - The number of dieline segments drops from N to 1.
     - Bounding box min/max coordinates are unchanged within tolerance.
     - Stroke colour in the saved PDF resolves to CMYK 0/1/0/0 with `/stans` separation.
   - Negative test: ensure non-target strokes remain untouched.

5. **Tooling / Debug Output**
   - CLI helper `python -m tools.dump_dieline --pdf path.pdf` that prints detected segments and bounding boxes (uses the new builder internals).
   - Provide `python -m tools.pymupdf_compound_path input.pdf output.pdf` to run the PyMuPDF rewrite from the command line.
   - Optional overlay export: add an option to draw the combined path to a new layer for manual verification.

6. **Documentation & Rollout**
   - Document the PyMuPDF workflow, how to run the analyzer, and how to add new colour aliases.
   - Update operational playbooks so production understands that compound-path fixes now rely on MuPDF (license considerations already satisfied via AGPL/commercial path?).

## Acceptance Criteria
- Running the pipeline on `6001857074-1_design_1.pdf` yields a PDF where:
  - The dieline layer contains exactly one stroked path (`page.get_drawings()` returns a single entry for that spot colour).
  - The path bounding-box coordinates match the original dieline within ±0.01 pt.
- Stroke colour is `/stans`, tint = 1, CMYK 0/1/0/0, overprint enabled.
- No unintended artwork is removed or shifted.
- Final content stream shows a single `/stans CS` → `1 SCN` → `0.5 w` → `S` sequence.
- Synthetic regression covers multi-subpath (outer + hole) scenarios.
- Analyzer CLI reports consistent path counts before/after the rewrite.

## Open Questions
- Should we support automatic gap-closing (joining endpoints within tolerance) or require designers to deliver closed paths? Recommend tolerance but log warnings when snapping occurs.
- How do we retain optional-content membership when segments come from multiple layers? (MuPDF’s `Shape.commit(keepOC=True)` honours a single current OCG; we may need to split by OCG when consolidating.)
- Do we need to maintain original stroke dash patterns or line joins? (Default to copying the attributes from the first segment unless specified otherwise.)

## Deliverables
- `compound_builder.py` (or similar) implementing the PyMuPDF consolidation.
- Updated processor integration and configuration wiring.
- Analyzer CLI + regression fixtures under `tests/data/`.
- Documentation (this spec + README section) outlining deployment and verification steps.
