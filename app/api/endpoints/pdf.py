import base64
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Query
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, Dict
from pathlib import Path
import zipfile
import csv
import json
import os
import tempfile
import shutil
from ...models.schemas import (
    PDFJobConfig, PDFAnalysisResult, PDFProcessingResponse,
    ErrorResponse, ShapeType, WindingRouteResponse, FontMode
)

# Helper: normalize incoming shape strings (synonyms -> enum values)
def _normalize_shape(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    mapping = {
        # expected
        'circle': 'circle',
        'rectangle': 'rectangle',
        'custom': 'custom',
        # synonyms
        'irregular': 'custom',
        'square': 'rectangle',
        'rect': 'rectangle',
        'oval': 'circle',
        'ellipse': 'circle',
    }
    return mapping.get(s, s)
from ...core.pdf_processor import PDFProcessor
from ...core.pdf_analyzer import PDFAnalyzer
from ...core.config import settings
from ...utils.winding_router import route_by_winding, route_by_winding_str


router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _to_float(value: object, default: float = 0.0) -> float:
    """Parse floats from strings like "40,0" or "40.0"; returns default on failure."""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            v = value.strip().replace(",", ".")
            return float(v)
    except Exception:
        pass
    return default


def _to_int_or_str(value: object) -> Optional[object]:
    """Coerce winding to int when possible; otherwise keep original string; None if empty."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if v == "":
            return None
        try:
            return int(v)
        except Exception:
            return v
    return value


def _detect_reseller(context_text: str, config: Dict[str, object]) -> bool:
    """Heuristic: detect reseller customers by name in path/zip name or JSON fields."""
    keywords = ("print.com", "helloprint", "drukwerkdeal", "cimpress")
    txt = (context_text or "").lower()
    if any(k in txt for k in keywords):
        return True
    reseller_keys = (
        "Customer", "customer",
        "Reseller", "reseller",
        "Client", "client",
        "Brand", "brand",
        "Company", "company",
        "Supplier", "supplier",
        "SupplierId", "supplierid"
    )
    for key in reseller_keys:
        val = config.get(key)
        if isinstance(val, str) and any(k in val.lower() for k in keywords):
            return True
    return False


@router.post("/analyze", response_model=PDFAnalysisResult)
async def analyze_pdf(
    pdf_file: UploadFile = File(...)
):
    """
    Analyze a PDF file and return information about its dimensions, trimbox, and dielines
    """
    # Validate file type
    if not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    # Check file size
    if pdf_file.size and pdf_file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes"
        )
    # Save uploaded file temporarily
    temp_file = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
            shutil.copyfileobj(pdf_file.file, temp_file)
        # Analyze PDF
        analyzer = PDFAnalyzer()
        analysis = analyzer.analyze_pdf(temp_path)
        return PDFAnalysisResult(**analysis)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing PDF: {str(e)}")
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.post("/process")
async def process_pdf(
    pdf_file: UploadFile = File(...),
    job_config: str = Form(...),
    return_json: bool = Query(
        False,
        description="Return a JSON payload (with base64 PDF) instead of a file download"
    ),
    fonts: str | None = Query(None, description="Font handling override: embed or outline"),
    remove_marks: bool | None = Query(None, description="Remove crop/registration marks"),
):
    """
    Process a PDF file with dieline modifications based on the job configuration

    Args:
        pdf_file: The PDF file to process
        job_config: JSON string containing job configuration
    """
    # Parse job configuration
    try:
        config_dict = json.loads(job_config)
        # Normalize shape synonyms before validation
        if 'shape' in config_dict:
            config_dict['shape'] = _normalize_shape(config_dict.get('shape'))
        job_config_obj = PDFJobConfig(**config_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in job_config: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid job configuration: {str(e)}")

    # Optional fonts override via query param
    if fonts is not None:
        try:
            job_config_obj.fonts = FontMode(fonts)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid fonts value; use 'embed' or 'outline'")
    if remove_marks is not None:
        job_config_obj.remove_marks = bool(remove_marks)

    # Validate file type
    if not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Save uploaded file temporarily
    temp_input_path = None
    try:
        # Create temporary file for input
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_input_path = temp_file.name
            shutil.copyfileobj(pdf_file.file, temp_file)

        # Process PDF
        processor = PDFProcessor()
        result = processor.process_pdf(temp_input_path, job_config_obj)

        if result['success']:
            # Return the processed PDF file
            output_path = result['output_path']

            # Create a proper filename
            base_name = os.path.splitext(pdf_file.filename)[0]
            output_filename = f"{base_name}_processed_{job_config_obj.reference}.pdf"

            headers = {
                'X-Processing-Reference': job_config_obj.reference,
                'X-Processing-Shape': job_config_obj.shape
            }

            # Add winding information if available
            if hasattr(job_config_obj, 'winding') and job_config_obj.winding is not None:
                try:
                    rotation_angle = route_by_winding(job_config_obj.winding)
                    headers['X-Winding-Value'] = str(job_config_obj.winding)
                    headers['X-Rotation-Angle'] = str(rotation_angle)
                    headers['X-Needs-Rotation'] = 'true' if rotation_angle != 0 else 'false'
                except ValueError:
                    # Invalid winding value, add header but no rotation info
                    headers['X-Winding-Value'] = str(job_config_obj.winding)
                    headers['X-Winding-Error'] = 'Invalid winding value'

            if return_json:
                with open(output_path, 'rb') as processed_file:
                    encoded_pdf = base64.b64encode(processed_file.read()).decode('ascii')
                analysis_payload = result.get('analysis')
                analysis_model = (
                    PDFAnalysisResult(**analysis_payload)
                    if isinstance(analysis_payload, dict)
                    else None
                )
                payload = PDFProcessingResponse(
                    success=True,
                    message=result['message'],
                    reference=result['reference'],
                    analysis=analysis_model,
                    processing_details=result.get('processing_details'),
                    processed_pdf_base64=encoded_pdf,
                )
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

                return JSONResponse(content=payload.model_dump())

            return FileResponse(
                output_path,
                media_type='application/pdf',
                filename=output_filename,
                headers=headers
            )
        else:
            # Return error response
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error=result['message'],
                    detail=result.get('error'),
                    reference=job_config_obj.reference
                ).dict()
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.unlink(temp_input_path)
