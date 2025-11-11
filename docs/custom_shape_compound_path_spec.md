# Custom Shape Compound Path – Implementation Status

This document records the delivered design for the PyMuPDF-based compound-path workflow. It updates the original implementation plan with the final wiring that now ships in `feature/pymupdf-compound-path-integration`.

## Goals Recap

The automation still targets the same outcomes that motivated the plan:

- Preserve the exact geometry of every dieline segment while merging split `/stans` paths.
- Emit a single stroked compound path using `/stans`, 100 % magenta, 0.5 pt, overprint on.
- Keep layer / optional content bindings intact so production tooling can continue to toggle dielines.
- Provide diagnostics that expose how many dieline segments were merged and whether the original artwork contained mixed layers.

## Delivered Architecture

| Area | Delivered Work |
| --- | --- |
| **Analyzer** | `PDFAnalyzer.analyze_pdf` now includes a `dieline_layers` block that reports every stroked segment (`layer`, colour tuple, width in mm, bounding box) plus a `layer_mismatch` flag when aliases were spread across multiple layers. |
| **Pipeline** | `PDFProcessor` invokes `PyMuPDFCompoundPathTool` for both custom and standard shape flows so that every outgoing PDF is normalized. The analyzer result returned from processing is the same enriched structure used by `/api/pdf/analyze`. |
| **API** | `/api/pdf/analyze` (`PDFAnalysisResult`) and `/api/pdf/process` (`PDFProcessingResponse`) surface the new schema. Processing responses add `X-Dieline-Layer-Mismatch` and `X-Dieline-Segment-Count` headers, plus an optional JSON mode (`return_json=true`) with a base64 payload for workflows that do not want a streamed file. |
| **CLI** | Two helpers live under `tools/`: `python -m tools.pymupdf_compound_path` runs the compound-path normaliser, and `python -m tools.dump_dieline` prints (or JSON-dumps) the `dieline_layers` report for ad-hoc QA. |
| **Tests** | `tests/test_api_dieline_layers.py` exercises the API wiring, asserting that the schema serialises correctly, JSON mode returns the analysis block, and HTTP headers reflect the mismatch flag. |

The earlier PyPDF-only tooling remains in place as a pre-pass for spot colour renaming. The PyMuPDF stream rewriting is responsible for geometry consolidation and overprint enforcement.

## Key Implementation Notes

1. **Layer Canonicalisation** – The analyzer lowercases and strips whitespace before comparing layer names against the canonical alias set (CutContour/KissCut/Stans/DieCut). Mixing any of these values, or combining them with unnamed layers, sets `layer_mismatch=true`.
2. **Colour Normalisation** – PyMuPDF reports colour components as device-space tuples. The analyzer normalises them into rounded floats so that downstream tooling can compare values without worrying about precision noise.
3. **API Compatibility** – Existing consumers that only cared about legacy keys (`spot_colors`, `detected_dielines`, etc.) keep working. The new fields are optional, with defaults that reflect the absence of detected dielines.
4. **Return JSON Mode** – When `return_json=true`, `/api/pdf/process` and `/api/pdf/process-with-json-file` read the generated PDF into memory, encode it as base64, clear the temporary file, and respond with a `PDFProcessingResponse`. This supports n8n and other orchestration workflows that prefer JSON payloads.
5. **Header Signals** – Even in file-download mode, clients can read `X-Dieline-Layer-Mismatch` and `X-Dieline-Segment-Count` to decide whether to flag the job for manual review.

## Operational Usage

1. **Diagnose a PDF**
   ```bash
   python -m tools.dump_dieline docs/fixtures/sample.pdf
   ```
   Inspect the mismatch flag, colour tuples, and bounding boxes to verify whether the dieline came in cleanly.

2. **Normalize a PDF Outside the API**
   ```bash
   python -m tools.pymupdf_compound_path input.pdf output.pdf
   ```
   This uses the same internals invoked by `PDFProcessor`, making it safe for manual patch-ups.

3. **Integrate With Automation**
   ```bash
   curl -X POST "http://localhost:8000/api/pdf/process?return_json=true" \
     -F "pdf_file=@input.pdf" \
     -F 'job_config={"reference":"QA-123","shape":"custom","width":50,"height":50}'
   ```
   Inspect `analysis.dieline_layers` and the `processed_pdf_base64` buffer in the response.

## Open Follow-Ups

- **OCG Preservation Audit** – The compound-path tool copies the first sequence’s graphics state, which should retain layer membership. We still need an integration test that verifies the `/OCProperties` wiring survives on real-world files with nested Form XObjects.
- **Tolerance-Based Stitching** – The current implementation assumes segments are already contiguous. Consider a future enhancement that snaps endpoints within a configurable tolerance and records the adjustment in the diagnostics.
- **Performance Benchmarks** – PyMuPDF runs quickly on one-page labels, but we should benchmark multi-page jobs and large sheet runs to decide whether batching (or selective processing) is required.

## References

- `app/utils/pymupdf_compound_path_tool.py` – stream rewriting and compound-path logic.
- `app/core/pdf_analyzer.py` – source of `dieline_layers` diagnostics.
- `tests/test_api_dieline_layers.py` – regression suite for schema and headers.
- `README.md` – updated with CLI usage, new headers, and JSON response details.
