"""
PDF Batch Processing Endpoint

Handles ZIP file processing with multiple PDFs and JSON configs.
"""

import base64
import csv
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ...core.config import settings
from ...core.pdf_processor import PDFProcessor
from ...models.schemas import PDFJobConfig, ShapeType
from ...utils.winding_router import route_by_winding_str
from .pdf_helpers import (
    detect_reseller,
    get_explicit_rotation,
    parse_job_config_from_json,
    to_float,
    to_int_or_str,
)

router = APIRouter()


def _safe_extract(zf: zipfile.ZipFile, target_dir: Path) -> None:
    """Safely extract ZIP contents, preventing path traversal."""
    for member in zf.infolist():
        dest_path = (target_dir / member.filename).resolve()
        if not str(dest_path).startswith(str(target_dir.resolve())):
            raise HTTPException(status_code=400, detail="Unsafe path in ZIP archive")
        if member.is_dir():
            dest_path.mkdir(parents=True, exist_ok=True)
            continue
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as src, open(dest_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


@router.post("/process-zip")
async def process_zip(
    zip_file: UploadFile = File(...),
    return_json: bool = Query(
        False,
        description="Return a JSON payload (with base64 ZIP) instead of a file download",
    ),
):
    """
    Process a ZIP containing PDFs (and optional per-file JSON metadata).

    - Each PDF is processed via the existing processor.
    - If a sibling JSON with the same basename exists, it is used for config.
    - Returns a ZIP with processed outputs and summary.csv.
    """
    if not zip_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed")

    if getattr(zip_file, "size", None) and zip_file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes",
        )

    temp_zip_path: Optional[str] = None
    extract_dir: Optional[Path] = None
    results_dir: Optional[Path] = None
    zip_basename = os.path.splitext(os.path.basename(zip_file.filename or "results"))[0]

    try:
        # Save uploaded ZIP
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tf:
            temp_zip_path = tf.name
            shutil.copyfileobj(zip_file.file, tf)

        # Setup directories
        extract_dir = Path(tempfile.mkdtemp(prefix="zip_extract_"))
        results_root = Path("zip_output")
        results_root.mkdir(parents=True, exist_ok=True)
        results_dir = results_root / f"{zip_basename}_processed"
        if results_dir.exists():
            shutil.rmtree(results_dir, ignore_errors=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        # Extract ZIP
        with zipfile.ZipFile(temp_zip_path, "r") as zf:
            _safe_extract(zf, extract_dir)

        # Process PDFs
        summary_rows, written_json_outputs = _process_zip_contents(
            extract_dir, results_dir, zip_basename
        )

        # Write summary CSV
        summary_csv_path = results_dir / "summary.csv"
        with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(summary_rows)

        # Create output ZIP
        zip_output_dir = Path("zip_output")
        zip_output_dir.mkdir(parents=True, exist_ok=True)
        output_zip_path = zip_output_dir / f"{zip_basename}_processed.zip"
        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in results_dir.rglob("*"):
                if entry.is_file():
                    arcname = entry.relative_to(results_dir)
                    zf.write(entry, arcname.as_posix())

        if return_json:
            with open(output_zip_path, "rb") as processed_zip:
                encoded_zip = base64.b64encode(processed_zip.read()).decode("ascii")
            try:
                os.unlink(output_zip_path)
            except OSError:
                pass
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Batch processed successfully",
                    "files_processed": len(summary_rows) - 1,  # Exclude header
                    "results_zip_base64": encoded_zip,
                }
            )

        return FileResponse(
            str(output_zip_path),
            media_type="application/zip",
            filename=f"{zip_basename}_processed.zip",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing ZIP: {str(e)}")
    finally:
        if temp_zip_path and os.path.exists(temp_zip_path):
            try:
                os.unlink(temp_zip_path)
            except OSError:
                pass
        for d in (extract_dir, results_dir):
            if isinstance(d, Path) and d.exists():
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except OSError:
                    pass


def _process_zip_contents(
    extract_dir: Path, results_dir: Path, zip_basename: str
) -> tuple[list, set]:
    """Process all PDFs in extracted ZIP directory."""
    all_pdfs = [p for p in extract_dir.rglob("*") if p.suffix.lower() == ".pdf"]
    pdf_paths = [
        p for p in all_pdfs
        if any(k in p.stem.lower() for k in ("design", "artwork"))
        and "jobsheet" not in p.stem.lower()
    ]
    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No PDF files found in ZIP")

    summary_rows = [[
        "filename", "reference", "shape", "success", "message",
        "winding_route", "layer_mismatch", "dieline_segment_count",
    ]]
    written_json_outputs: set[str] = set()
    for pdf_path in pdf_paths:
        summary_rows.append(_process_single_pdf(
            pdf_path, results_dir, zip_basename, written_json_outputs
        ))
    return summary_rows, written_json_outputs


def _process_single_pdf(
    pdf_path: Path, results_dir: Path, zip_basename: str, written_json_outputs: set
) -> list:
    """Process a single PDF from the ZIP."""
    base = pdf_path.stem

    # Find sibling JSON
    chosen_json_path = _find_sibling_json(pdf_path)
    if chosen_json_path is None:
        return [pdf_path.name, base, "", "skipped", "missing sibling json", "", "", ""]

    # Parse JSON config
    try:
        with open(chosen_json_path, "rb") as f:
            original_json_bytes = f.read()
            config_dict = json.loads(original_json_bytes)

        job_config_data = parse_job_config_from_json(config_dict, base)
        explicit_rotate = get_explicit_rotation(config_dict)

        # Apply reseller rotation logic
        reseller_detected = detect_reseller(zip_basename, config_dict)
        applied_rotation = _compute_rotation(
            explicit_rotate, reseller_detected, job_config_data
        )

        if applied_rotation is not None:
            job_config_data["rotate_degrees"] = applied_rotation
        if reseller_detected and applied_rotation in (90, 270):
            job_config_data["width"], job_config_data["height"] = (
                job_config_data["height"],
                job_config_data["width"],
            )
        if reseller_detected:
            job_config_data["winding"] = 2

        job_config_obj = PDFJobConfig(**job_config_data)

    except Exception:
        return [pdf_path.name, base, "", "skipped", "malformed json", "", "", ""]

    # Process PDF
    processor = PDFProcessor()
    result = processor.process_pdf(str(pdf_path), job_config_obj)

    success = bool(result.get("success"))
    message = str(result.get("message", ""))
    output_path = result.get("output_path")
    updated_job_config = result.get("updated_job_config")

    # Save normalized JSON
    _save_normalized_json(
        config_dict, updated_job_config, chosen_json_path,
        base, results_dir, written_json_outputs,
    )

    # Save processed PDF
    if success and isinstance(output_path, str) and os.path.exists(output_path):
        base_name = os.path.splitext(os.path.basename(pdf_path.name))[0]
        out_filename = f"{base_name}.processed.pdf"
        shutil.copy2(output_path, str(results_dir / out_filename))
        try:
            os.unlink(output_path)
        except OSError:
            pass

    # Extract metadata for summary
    analysis_payload = result.get("analysis")
    layer_mismatch = None
    segment_count = None
    winding_route = None
    shape_str = None

    if isinstance(analysis_payload, dict):
        dieline_layers = analysis_payload.get("dieline_layers", {})
        if isinstance(dieline_layers, dict):
            layer_mismatch = dieline_layers.get("layer_mismatch")
            segments = dieline_layers.get("segments")
            if isinstance(segments, list):
                segment_count = len(segments)

    processing_details = result.get("processing_details")
    if isinstance(processing_details, dict):
        winding_route = processing_details.get("winding_route")
        shape_str = processing_details.get("shape_type")

    return [
        pdf_path.name,
        job_config_obj.reference,
        shape_str or job_config_obj.shape,
        "true" if success else "false",
        message,
        str(winding_route) if winding_route is not None else "",
        "true" if layer_mismatch else ("false" if layer_mismatch is not None else ""),
        str(segment_count) if segment_count is not None else "",
    ]


def _find_sibling_json(pdf_path: Path) -> Optional[Path]:
    """Find the sibling JSON file for a PDF."""
    metadata_json = pdf_path.with_suffix(".json")
    if metadata_json.exists():
        return metadata_json

    order_prefix = pdf_path.stem.split("_")[0]
    sibling_jsons = list(pdf_path.parent.glob("*.json"))
    matched = [j for j in sibling_jsons if j.stem.startswith(order_prefix)]
    if matched:
        return sorted(matched, key=lambda p: len(p.stem))[0]
    elif len(sibling_jsons) == 1:
        return sibling_jsons[0]
    return None


def _compute_rotation(
    explicit_rotate: Optional[int],
    reseller_detected: bool,
    job_config_data: dict,
) -> Optional[int]:
    """Compute rotation angle based on config and reseller detection."""
    if explicit_rotate is not None:
        return explicit_rotate if explicit_rotate in (0, 90, 180, 270) else 0

    if reseller_detected and job_config_data.get("winding") is not None:
        try:
            return route_by_winding_str(job_config_data["winding"])
        except Exception:
            return None
    return None


def _save_normalized_json(
    config_dict: dict, updated_job_config, chosen_json_path: Optional[Path],
    base: str, results_dir: Path, written_json_outputs: set,
):
    """Save normalized JSON alongside processed PDF."""
    if updated_job_config is None:
        return

    try:
        normalized = dict(config_dict)

        # Update winding and dimensions using first available key
        for keys, value in [
            (("Winding", "winding"), updated_job_config.winding),
            (("Width", "width"), float(updated_job_config.width)),
            (("Height", "height"), float(updated_job_config.height)),
        ]:
            for key in keys:
                if key in normalized:
                    normalized[key] = value
                    break
            else:
                normalized[keys[0]] = value

        # Add rotation if applied
        if getattr(updated_job_config, "rotate_degrees", None) is not None:
            if not any(k in config_dict for k in ("Rotate", "rotate", "Orientation")):
                normalized["Rotate"] = updated_job_config.rotate_degrees

        json_bytes = json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8")
        results_dir.mkdir(parents=True, exist_ok=True)
        json_stem = chosen_json_path.stem if chosen_json_path else base
        json_output_name = f"{json_stem}.json"
        if json_output_name not in written_json_outputs:
            with open(results_dir / json_output_name, "wb") as jf:
                jf.write(json_bytes)
            written_json_outputs.add(json_output_name)
    except Exception as e:
        print(f"Warning: Failed to save normalized JSON: {e}")

