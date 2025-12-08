"""
PDF API Endpoints

Main endpoints for PDF analysis and processing.
Batch processing in pdf_batch.py, repair in pdf_repair_endpoints.py.
"""

import base64
import json
import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ...core.config import settings
from ...core.pdf_analyzer import PDFAnalyzer
from ...core.pdf_processor import PDFProcessor
from ...models.schemas import (
    ErrorResponse,
    FontMode,
    PDFAnalysisResult,
    PDFJobConfig,
    PDFProcessingResponse,
    WindingRouteResponse,
)
from ...utils.winding_router import route_by_winding, route_by_winding_str
from .pdf_batch import router as batch_router
from .pdf_helpers import (
    detect_reseller,
    get_explicit_rotation,
    normalize_shape,
    parse_job_config_from_json,
)
from .pdf_repair_endpoints import router as repair_router

router = APIRouter(prefix="/api/pdf", tags=["pdf"])
router.include_router(batch_router)
router.include_router(repair_router)


@router.post("/analyze", response_model=PDFAnalysisResult)
async def analyze_pdf(pdf_file: UploadFile = File(...)):
    """Analyze a PDF file and return dimensions, trimbox, and dieline info."""
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    if pdf_file.size and pdf_file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes",
        )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_path = temp_file.name
            shutil.copyfileobj(pdf_file.file, temp_file)

        analyzer = PDFAnalyzer()
        analysis = analyzer.analyze_pdf(temp_path)
        return PDFAnalysisResult(**analysis)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing PDF: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.post("/process")
async def process_pdf(
    pdf_file: UploadFile = File(...),
    job_config: str = Form(...),
    return_json: bool = Query(False, description="Return JSON with base64 PDF"),
    fonts: str | None = Query(None, description="Font handling: embed or outline"),
    remove_marks: bool | None = Query(None, description="Remove crop/registration marks"),
):
    """Process a PDF file with dieline modifications based on job configuration."""
    # Validate file extension first
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Enforce max file size
    if pdf_file.size and pdf_file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes",
        )

    try:
        config_dict = json.loads(job_config)
        if "shape" in config_dict:
            config_dict["shape"] = normalize_shape(config_dict.get("shape"))
        job_config_obj = PDFJobConfig(**config_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid job configuration: {str(e)}")

    if fonts is not None:
        try:
            job_config_obj.fonts = FontMode(fonts)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid fonts value")
    if remove_marks is not None:
        job_config_obj.remove_marks = bool(remove_marks)

    temp_input_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_input_path = temp_file.name
            shutil.copyfileobj(pdf_file.file, temp_file)

        processor = PDFProcessor()
        result = processor.process_pdf(temp_input_path, job_config_obj)

        if result["success"]:
            return _build_process_response(
                result, job_config_obj, pdf_file.filename, return_json
            )
        else:
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error=result["message"],
                    detail=result.get("error"),
                    reference=job_config_obj.reference,
                ).dict(),
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.unlink(temp_input_path)


@router.post("/process-with-json-file")
async def process_pdf_with_json_file(
    pdf_file: UploadFile = File(...),
    json_file: UploadFile = File(...),
    return_json: bool = Query(False, description="Return JSON with base64 PDF"),
    fonts: str | None = Query(None, description="Font handling: embed or outline"),
    remove_marks: bool | None = Query(None, description="Remove crop/registration marks"),
):
    """Process a PDF file with a separate JSON configuration file."""
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file must have .pdf extension")
    if not json_file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Config file must have .json extension")

    # Enforce max file size on PDF upload
    if pdf_file.size and pdf_file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes",
        )

    try:
        json_content = await json_file.read()
        config_dict = json.loads(json_content)
        job_config_data = parse_job_config_from_json(config_dict)
        explicit_rotate = get_explicit_rotation(config_dict)

        reseller_detected = detect_reseller(
            f"{pdf_file.filename} {json_file.filename}", config_dict
        )

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

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing config: {str(e)}")

    if fonts is not None:
        try:
            job_config_obj.fonts = FontMode(fonts)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid fonts value")
    if remove_marks is not None:
        job_config_obj.remove_marks = bool(remove_marks)

    temp_input_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_input_path = temp_file.name
            pdf_content = await pdf_file.read()
            temp_file.write(pdf_content)

        processor = PDFProcessor()
        result = processor.process_pdf(temp_input_path, job_config_obj)

        if result["success"]:
            return _build_process_response(
                result, job_config_obj, pdf_file.filename, return_json
            )
        else:
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error=result["message"],
                    detail=result.get("error"),
                    reference=job_config_obj.reference,
                ).dict(),
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.unlink(temp_input_path)


@router.get("/route-by-winding/{winding_value}", response_model=WindingRouteResponse)
async def get_route_by_winding(winding_value: str):
    """Return the route angle (0, 90, 180, 270) mapped from a winding value."""
    try:
        route = route_by_winding_str(winding_value)
        return WindingRouteResponse(winding_value=str(winding_value), route=route)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _compute_rotation(
    explicit_rotate: int | None, reseller_detected: bool, job_config_data: dict
) -> int | None:
    """Compute rotation based on explicit value or reseller winding."""
    if explicit_rotate is not None:
        return explicit_rotate if explicit_rotate in (0, 90, 180, 270) else 0

    if reseller_detected and job_config_data.get("winding") is not None:
        try:
            return route_by_winding_str(job_config_data["winding"])
        except Exception:
            return None
    return None


def _build_process_response(
    result: dict, job_config_obj: PDFJobConfig, filename: str, return_json: bool
):
    """Build response for successful PDF processing."""
    output_path = result["output_path"]
    base_name = os.path.splitext(filename)[0]
    output_filename = f"{base_name}_processed_{job_config_obj.reference}.pdf"

    headers = {
        "X-Processing-Reference": job_config_obj.reference,
        "X-Processing-Shape": job_config_obj.shape,
    }

    winding_route = result.get("processing_details", {}).get("winding_route")
    if winding_route is not None:
        headers["X-Winding-Route"] = str(winding_route)

    if job_config_obj.winding is not None:
        try:
            rotation_angle = route_by_winding(job_config_obj.winding)
            headers["X-Winding-Value"] = str(job_config_obj.winding)
            headers["X-Rotation-Angle"] = str(rotation_angle)
            headers["X-Needs-Rotation"] = "true" if rotation_angle != 0 else "false"
        except ValueError:
            headers["X-Winding-Value"] = str(job_config_obj.winding)
            headers["X-Winding-Error"] = "Invalid winding value"

    analysis_payload = result.get("analysis")
    analysis_model = (
        PDFAnalysisResult(**analysis_payload)
        if isinstance(analysis_payload, dict)
        else None
    )

    if isinstance(analysis_payload, dict):
        dieline_layers = analysis_payload.get("dieline_layers", {})
        if isinstance(dieline_layers, dict):
            mismatch = dieline_layers.get("layer_mismatch")
            if mismatch is not None:
                headers["X-Dieline-Layer-Mismatch"] = "true" if mismatch else "false"
            segments = dieline_layers.get("segments")
            if isinstance(segments, list):
                headers["X-Dieline-Segment-Count"] = str(len(segments))

    if return_json:
        with open(output_path, "rb") as processed_file:
            encoded_pdf = base64.b64encode(processed_file.read()).decode("ascii")

        payload = PDFProcessingResponse(
            success=True,
            message=result["message"],
            reference=result["reference"],
            analysis=analysis_model,
            processing_details=result.get("processing_details"),
            processed_pdf_base64=encoded_pdf,
        )

        try:
            os.unlink(output_path)
        except OSError:
            pass

        return JSONResponse(content=payload.model_dump())

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_filename,
        headers=headers,
    )
