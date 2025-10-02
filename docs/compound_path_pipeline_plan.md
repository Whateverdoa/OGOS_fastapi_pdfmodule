# Compound Path Pipeline Follow-Up Plan

This document captures the remaining work for the PyMuPDF-based compound-path workflow so the next Codex instance can pick up where we left off.

## Current Status (2025-10-02)
- `PDFAnalyzer` reports detailed `dieline_layers` metadata and flags `layer_mismatch` when multiple dieline segments span different layers/aliases.
- `PyMuPDFCompoundPathTool` merges all `/stans`/kisscut stroke segments into a single path, renames to `/stans`, enforces 100% magenta, 0.5 pt, overprint.
- `PDFProcessor` invokes the compound pass for **both** custom and standard shape flows, so every processed PDF is normalised.
- CLI `python -m tools.pymupdf_compound_path` exists for manual use.

## Remaining Tasks
1. **API Schema & Response Wiring**
   - Extend `PDFAnalysisResult` to expose the new `dieline_layers` block (segments + mismatch flag).
   - Ensure `/api/pdf/analyze` returns the richer structure and `/api/pdf/process` includes the same in its response payload.
   - Update any frontend / integration tests or documentation consuming the analysis output.

2. **Optional CLI Diagnostics**
   - Provide a helper (e.g. `python -m tools.dump_dieline`) that prints the `dieline_layers` info for a local PDF. Useful for QA and manual checks.

3. **Documentation Refresh**
   - README / ops guide: mention the analyzer mismatch flag, the automatic PyMuPDF pass, and how to run the new CLI.
   - Link to `docs/custom_shape_compound_path_spec.md` from the main documentation index.

4. **Testing**
   - Add regression tests that cover the new schema serialisation and ensure `layer_mismatch` propagates through the API response.
   - Optionally add an integration test that runs the processor end-to-end on a fixture with split dielines and asserts a single `/stans` stroke afterwards.

## Branch & Handoff
- Continue development on the branch `feature/pymupdf-compound-path-integration` (created alongside this plan).
- Commits currently in this branch encapsulate the PyMuPDF tool, analyzer enhancements, and pipeline integration.
- Next steps should start by wiring the schema/API changes on the same branch unless a new feature branch is required.

Reach out to `PDFProcessor` owners if additional orchestration logic is needed.
