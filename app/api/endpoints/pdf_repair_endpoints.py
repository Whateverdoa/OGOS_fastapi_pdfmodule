"""
PDF Repair and Validation Endpoints

Endpoints for validating and repairing corrupt PDFs (q/Q stack issues).
"""

import base64
import os
import shutil
import tempfile

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ...utils.pdf_repair import PDFRepair


def _cleanup_temp_file(path: str) -> None:
    """Background task to remove temporary files after response is sent."""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass

router = APIRouter()


@router.post("/validate")
async def validate_pdf_content(pdf_file: UploadFile = File(...)):
    """
    Validate a PDF file for content stream issues.

    Checks for:
    - q/Q operator imbalance (graphics state save/restore)
    - Stack underflows (Q without matching q)
    - Other content stream anomalies

    These issues can cause parsing failures in strict PDF processors
    like iText ("Stack empty" exception).
    """
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            temp_path = tf.name
            shutil.copyfileobj(pdf_file.file, tf)

        repair = PDFRepair()
        result = repair.validate_pdf(temp_path)

        return JSONResponse(
            content={
                "filename": pdf_file.filename,
                "is_valid": result.is_valid,
                "has_stack_imbalance": result.has_stack_imbalance,
                "total_q_operators": result.total_q_ops,
                "total_Q_operators": result.total_Q_ops,
                "stack_underflows": result.stack_underflows,
                "page_issues": result.page_issues,
                "warnings": result.warnings,
                "recommendation": (
                    "PDF is valid"
                    if result.is_valid
                    else "PDF has content stream issues. Use /api/pdf/repair to fix."
                ),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.post("/repair")
async def repair_pdf_content(
    pdf_file: UploadFile = File(...),
    return_json: bool = Query(
        False, description="Return JSON with base64-encoded PDF instead of file download"
    ),
    background_tasks: BackgroundTasks = None,
):
    """
    Repair a PDF file with content stream issues.

    Attempts multiple repair strategies:
    1. Ghostscript pdfwrite (rewrites content streams)
    2. PyMuPDF garbage collection
    3. PyMuPDF page reconstruction

    Use /api/pdf/validate first to check if repair is needed.
    """
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_input = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            temp_input = tf.name
            shutil.copyfileobj(pdf_file.file, tf)

        repair = PDFRepair()
        result = repair.repair_pdf(temp_input)

        if not result.success:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": result.error or "Repair failed",
                    "validation_before": _format_validation(result.validation_before),
                },
            )

        temp_output = result.output_path
        base_name = os.path.splitext(pdf_file.filename)[0]
        output_filename = f"{base_name}_repaired.pdf"

        response_data = {
            "success": True,
            "method_used": result.method_used,
            "validation_before": _format_validation_full(result.validation_before),
            "validation_after": _format_validation_full(result.validation_after),
        }

        if return_json:
            with open(temp_output, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            response_data["repaired_pdf_base64"] = encoded
            # Clean up temp output after reading into memory
            _cleanup_temp_file(temp_output)
            return JSONResponse(content=response_data)

        # Schedule cleanup of temp output after response is sent
        if background_tasks:
            background_tasks.add_task(_cleanup_temp_file, temp_output)

        return FileResponse(
            temp_output,
            media_type="application/pdf",
            filename=output_filename,
            headers={
                "X-Repair-Method": result.method_used or "unknown",
                "X-Repair-Success": "true",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Repair error: {str(e)}")
    finally:
        if temp_input and os.path.exists(temp_input):
            os.unlink(temp_input)


def _format_validation(validation) -> dict | None:
    """Format validation result for error response."""
    if validation is None:
        return None
    return {
        "is_valid": validation.is_valid,
        "stack_underflows": validation.stack_underflows,
    }


def _format_validation_full(validation) -> dict | None:
    """Format full validation result for success response."""
    if validation is None:
        return None
    return {
        "is_valid": validation.is_valid,
        "q_ops": validation.total_q_ops,
        "Q_ops": validation.total_Q_ops,
        "stack_underflows": validation.stack_underflows,
    }

