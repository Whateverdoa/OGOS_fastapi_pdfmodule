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
    remove_marks: bool | None = Query(None, description="Remove crop/registration marks")
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

            # Prepare headers
            headers = {
                'X-Processing-Reference': job_config_obj.reference,
                'X-Processing-Shape': job_config_obj.shape
            }
            
            # Add winding route information
            winding_route = (
                result.get('processing_details', {}).get('winding_route')
                if isinstance(result.get('processing_details'), dict) else None
            )
            if winding_route is not None:
                headers['X-Winding-Route'] = str(winding_route)
            
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

            analysis_payload = result.get('analysis')
            analysis_model = (
                PDFAnalysisResult(**analysis_payload)
                if isinstance(analysis_payload, dict)
                else None
            )

            if isinstance(analysis_payload, dict):
                layer_mismatch = (
                    analysis_payload.get('dieline_layers', {})
                    if isinstance(analysis_payload.get('dieline_layers'), dict)
                    else {}
                )
                mismatch_flag = layer_mismatch.get('layer_mismatch')
                if mismatch_flag is not None:
                    headers['X-Dieline-Layer-Mismatch'] = 'true' if mismatch_flag else 'false'

                segments = layer_mismatch.get('segments')
                if isinstance(segments, list):
                    headers['X-Dieline-Segment-Count'] = str(len(segments))

            if return_json:
                with open(output_path, 'rb') as processed_file:
                    encoded_pdf = base64.b64encode(processed_file.read()).decode('ascii')
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


@router.get("/route-by-winding/{winding_value}", response_model=WindingRouteResponse)
async def get_route_by_winding(winding_value: str):
    """
    Return the route angle (0, 90, 180, 270) mapped from a winding value.

    Accepts either numeric or string inputs (1-8). Returns 400 if unmapped.
    """
    try:
        route = route_by_winding_str(winding_value)
        return WindingRouteResponse(winding_value=str(winding_value), route=route)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/process-with-json-file")
async def process_pdf_with_json_file(
    pdf_file: UploadFile = File(...),
    json_file: UploadFile = File(...),
    return_json: bool = Query(
        False,
        description="Return a JSON payload (with base64 PDF) instead of a file download"
    ),
    fonts: str | None = Query(None, description="Font handling override: embed or outline"),
    remove_marks: bool | None = Query(None, description="Remove crop/registration marks")
):
    """
    Process a PDF file with a separate JSON configuration file
    """
    # Validate file types
    if not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF file must have .pdf extension")
        
    if not json_file.filename.lower().endswith('.json'):
        raise HTTPException(status_code=400, detail="Configuration file must have .json extension")
        
    # Read JSON configuration
    try:
        json_content = await json_file.read()
        config_dict = json.loads(json_content)
        
        # Map JSON fields to PDFJobConfig
        # Handle both uppercase and lowercase shape values and synonyms
        raw_shape = config_dict.get('Shape', config_dict.get('shape', ''))
        shape_value = _normalize_shape(raw_shape)
        if shape_value is None:
            # Fallback to old logic if normalization returns None
            shape_value = config_dict.get('Shape', config_dict.get('shape', '')).lower()
            if shape_value in ('irregular', 'custom_shape', 'freeform'):
                shape_value = ShapeType.custom.value
        
        # Extract optional explicit rotation
        rotate_val_raw = config_dict.get('Rotate', config_dict.get('rotate', config_dict.get('Orientation')))
        explicit_rotate = None
        if rotate_val_raw is not None:
            try:
                explicit_rotate = int(round(_to_float(rotate_val_raw, 0.0)))
            except Exception:
                explicit_rotate = None

        job_config_data = {
            'reference': config_dict.get('ReferenceAtCustomer', config_dict.get('reference', '')),
            'description': config_dict.get('Description', ''),
            'shape': shape_value,
            'width': _to_float(config_dict.get('Width', config_dict.get('width', 0))),
            'height': _to_float(config_dict.get('Height', config_dict.get('height', 0))),
            'radius': _to_float(config_dict.get('Radius', config_dict.get('radius', 0))),
            'winding': _to_int_or_str(config_dict.get('Winding', config_dict.get('winding'))),
            'substrate': config_dict.get('Substrate', config_dict.get('substrate')),
            'adhesive': config_dict.get('Adhesive', config_dict.get('adhesive')),
            'colors': config_dict.get('Colors', config_dict.get('colors')),
            'fonts': config_dict.get('Fonts', config_dict.get('fonts', 'embed')),
            'remove_marks': config_dict.get('RemoveMarks', config_dict.get('remove_marks', config_dict.get('removeMarks', False)))
        }

        # Reseller detection from filenames or JSON fields
        reseller_detected = _detect_reseller(
            f"{pdf_file.filename} {json_file.filename}",  # type: ignore[arg-type]
            config_dict  # type: ignore[arg-type]
        )

        # Rotation logic: explicit wins; else if reseller and winding provided, map from winding
        applied_rotation = None
        if explicit_rotate is not None:
            applied_rotation = explicit_rotate if explicit_rotate in (0, 90, 180, 270) else 0
        elif reseller_detected and job_config_data.get('winding') is not None:
            try:
                applied_rotation = route_by_winding_str(job_config_data['winding'])  # type: ignore[index]
            except Exception:
                applied_rotation = None
        if applied_rotation is not None:
            job_config_data['rotate_degrees'] = applied_rotation
        if reseller_detected and applied_rotation in (90, 270):
            job_config_data['width'], job_config_data['height'] = (
                job_config_data['height'],
                job_config_data['width'],
            )

        # Force reseller winding normalization to 2
        if reseller_detected:
            job_config_data['winding'] = 2

        job_config_obj = PDFJobConfig(**job_config_data)
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing configuration: {str(e)}")
        
    # Optional fonts override via query param
    if fonts is not None:
        try:
            job_config_obj.fonts = FontMode(fonts)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid fonts value; use 'embed' or 'outline'")
    if remove_marks is not None:
        job_config_obj.remove_marks = bool(remove_marks)

    # Save PDF temporarily and process
    temp_input_path = None
    try:
        # Create temporary file for input
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_input_path = temp_file.name
            pdf_content = await pdf_file.read()
            temp_file.write(pdf_content)
            
        # Process PDF
        processor = PDFProcessor()
        result = processor.process_pdf(temp_input_path, job_config_obj)
        
        if result['success']:
            # Return the processed PDF file
            output_path = result['output_path']

            # Create a proper filename
            base_name = os.path.splitext(pdf_file.filename)[0]
            output_filename = f"{base_name}_processed_{job_config_obj.reference}.pdf"

            # Prepare headers
            headers = {
                'X-Processing-Reference': job_config_obj.reference,
                'X-Processing-Shape': job_config_obj.shape
            }
            
            # Add winding route information
            winding_route = (
                result.get('processing_details', {}).get('winding_route')
                if isinstance(result.get('processing_details'), dict) else None
            )
            if winding_route is not None:
                headers['X-Winding-Route'] = str(winding_route)
            
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

            analysis_payload = result.get('analysis')
            analysis_model = (
                PDFAnalysisResult(**analysis_payload)
                if isinstance(analysis_payload, dict)
                else None
            )

            if isinstance(analysis_payload, dict):
                layer_mismatch = (
                    analysis_payload.get('dieline_layers', {})
                    if isinstance(analysis_payload.get('dieline_layers'), dict)
                    else {}
                )
                mismatch_flag = layer_mismatch.get('layer_mismatch')
                if mismatch_flag is not None:
                    headers['X-Dieline-Layer-Mismatch'] = 'true' if mismatch_flag else 'false'

                segments = layer_mismatch.get('segments')
                if isinstance(segments, list):
                    headers['X-Dieline-Segment-Count'] = str(len(segments))

            if return_json:
                with open(output_path, 'rb') as processed_file:
                    encoded_pdf = base64.b64encode(processed_file.read()).decode('ascii')

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
        # Clean up temporary input file
        if temp_input_path and os.path.exists(temp_input_path):
            os.unlink(temp_input_path)


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
    - If a sibling JSON with the same basename exists, it is copied back
      untouched into the results alongside the processed PDF.
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
    zip_basename: str = os.path.splitext(os.path.basename(zip_file.filename or "results"))[0]

    def safe_extract(zf: zipfile.ZipFile, target_dir: Path) -> None:
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

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tf:
            temp_zip_path = tf.name
            shutil.copyfileobj(zip_file.file, tf)

        extract_dir = Path(tempfile.mkdtemp(prefix="zip_extract_"))
        # Save results to a deterministic host-mapped folder: zip_output/<zip_basename>_processed
        results_root = Path("zip_output")
        results_root.mkdir(parents=True, exist_ok=True)
        results_dir = results_root / f"{zip_basename}_processed"
        if results_dir.exists():
            shutil.rmtree(results_dir, ignore_errors=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_zip_path, "r") as zf:
            safe_extract(zf, extract_dir)

        # Discover PDFs recursively (case-insensitive extension)
        all_pdfs = [
            p for p in extract_dir.rglob("*")
            if p.is_file() and p.suffix.lower() == ".pdf"
        ]
        pdf_name = lambda s: s.lower()
        pdf_paths = [
            p for p in all_pdfs
            if (("design" in pdf_name(p.stem)) or ("artwork" in pdf_name(p.stem)))
            and ("jobsheet" not in pdf_name(p.stem))
        ]
        all_jsons = [p for p in extract_dir.rglob("*.json") if p.is_file()]
        if not pdf_paths:
            raise HTTPException(status_code=400, detail="No PDF files found in ZIP")

        summary_rows = [[
            "filename",
            "reference",
            "shape",
            "success",
            "message",
            "winding_route",
            "layer_mismatch",
            "dieline_segment_count",
        ]]
        written_json_outputs: set[str] = set()

        for pdf_path in pdf_paths:
            base = pdf_path.stem
            metadata_json = pdf_path.with_suffix(".json")
            # Jobsheets already excluded above

            job_config_obj = None
            original_json_bytes: Optional[bytes] = None
            normalized_json_bytes: Optional[bytes] = None
            chosen_json_path: Optional[Path] = None
            # Only accept sibling JSON; if exact match missing, try order-number match
            if metadata_json.exists():
                chosen_json_path = metadata_json
            else:
                # Try to match by shared order number prefix (before first underscore)
                order_prefix = base.split("_")[0]
                sibling_jsons = list(pdf_path.parent.glob("*.json"))
                matched = [j for j in sibling_jsons if j.stem.startswith(order_prefix)]
                if matched:
                    # Prefer the shortest stem (closest match)
                    chosen_json_path = sorted(matched, key=lambda p: len(p.stem))[0]
                elif len(sibling_jsons) == 1:
                    # If exactly one JSON exists in the folder, treat it as sibling
                    chosen_json_path = sibling_jsons[0]
                else:
                    summary_rows.append([
                        pdf_path.name,
                        base,
                        "",
                        "skipped",
                        "missing sibling json",
                        "",
                        "",
                        "",
                    ])
                    continue

            if chosen_json_path is not None:
                try:
                    with open(chosen_json_path, "rb") as f:
                        original_json_bytes = f.read()
                        config_dict = json.loads(original_json_bytes)

                    shape_value = config_dict.get("Shape", config_dict.get("shape", "")).lower()
                    if shape_value in ("irregular", "custom_shape", "freeform"):
                        shape_value = ShapeType.custom.value
                    # Optional explicit rotation in JSON
                    rotate_val_raw = config_dict.get("Rotate", config_dict.get("rotate", config_dict.get("Orientation")))
                    explicit_rotate: Optional[int] = None
                    if rotate_val_raw is not None:
                        try:
                            explicit_rotate = int(round(_to_float(rotate_val_raw, 0.0)))
                        except Exception:
                            explicit_rotate = None

                    job_config_data = {
                        "reference": config_dict.get("ReferenceAtCustomer", config_dict.get("reference", base)),
                        "description": config_dict.get("Description", ""),
                        "shape": shape_value,
                        "width": _to_float(config_dict.get("Width", config_dict.get("width", 0))),
                        "height": _to_float(config_dict.get("Height", config_dict.get("height", 0))),
                        "radius": _to_float(config_dict.get("Radius", config_dict.get("radius", 0))),
                        "winding": _to_int_or_str(config_dict.get("Winding", config_dict.get("winding"))),
                        "substrate": config_dict.get("Substrate", config_dict.get("substrate")),
                        "adhesive": config_dict.get("Adhesive", config_dict.get("adhesive")),
                        "colors": config_dict.get("Colors", config_dict.get("colors")),
                    }
                    # Reseller auto-rotation if no explicit rotate
                    reseller_detected = _detect_reseller(zip_basename, config_dict)  # type: ignore[arg-type]
                    applied_rotation: Optional[int] = None
                    if explicit_rotate is not None:
                        applied_rotation = explicit_rotate if explicit_rotate in (0, 90, 180, 270) else 0
                    elif reseller_detected and job_config_data.get("winding") is not None:
                        try:
                            applied_rotation = route_by_winding_str(job_config_data["winding"])  # type: ignore[arg-type]
                        except Exception:
                            applied_rotation = None
                    swap_dimensions = reseller_detected and applied_rotation in (90, 270)
                    if applied_rotation is not None:
                        job_config_data["rotate_degrees"] = applied_rotation
                    if swap_dimensions:
                        job_config_data["width"], job_config_data["height"] = (
                            job_config_data["height"],
                            job_config_data["width"],
                        )
                    # Force reseller winding normalization to 2 (after applying rotation)
                    if reseller_detected:
                        job_config_data["winding"] = 2

                    job_config_obj = PDFJobConfig(**job_config_data)

                    # Prepare normalized JSON for reseller: set winding=2 and applied rotation if any
                    normalized_json_bytes = None
                    if reseller_detected:
                        try:
                            normalized = dict(config_dict)
                            # Set winding to 2 using existing key if present
                            if "Winding" in normalized:
                                normalized["Winding"] = 2
                            elif "winding" in normalized:
                                normalized["winding"] = 2
                            else:
                                normalized["Winding"] = 2
                            # Set rotation if applied and not explicitly provided
                            if applied_rotation is not None:
                                if not any(k in config_dict for k in ("Rotate", "rotate", "Orientation")):
                                    normalized["Rotate"] = applied_rotation
                            if swap_dimensions:
                                swapped_width = job_config_data["width"]
                                swapped_height = job_config_data["height"]
                                if "Width" in normalized:
                                    normalized["Width"] = swapped_width
                                if "width" in normalized:
                                    normalized["width"] = swapped_width
                                if "Height" in normalized:
                                    normalized["Height"] = swapped_height
                                if "height" in normalized:
                                    normalized["height"] = swapped_height
                            normalized_json_bytes = json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8")
                        except Exception as e:
                            print(f"Warning: Failed to create normalized JSON for reseller: {e}")
                            normalized_json_bytes = None
                except Exception:
                    summary_rows.append([
                        pdf_path.name,
                        base,
                        "",
                        "skipped",
                        "malformed json",
                        "",
                        "",
                        "",
                    ])
                    continue

            processor = PDFProcessor()
            result = processor.process_pdf(str(pdf_path), job_config_obj)

            success = bool(result.get("success"))
            message = str(result.get("message", ""))
            output_path = result.get("output_path")

            # Save original/normalized JSON next to processed output (once per config)
            if original_json_bytes is not None:
                results_dir.mkdir(parents=True, exist_ok=True)
                # Save exactly one JSON per configuration: prefer normalized reseller JSON when available.
                json_bytes_to_write = normalized_json_bytes or original_json_bytes
                json_stem = None
                if chosen_json_path is not None:
                    json_stem = chosen_json_path.stem
                if not json_stem:
                    json_stem = base
                json_output_name = f"{json_stem}.json"
                if json_output_name not in written_json_outputs:
                    with open(results_dir / json_output_name, "wb") as jf:
                        jf.write(json_bytes_to_write)
                    written_json_outputs.add(json_output_name)

            if success and isinstance(output_path, str) and os.path.exists(output_path):
                base_name = os.path.splitext(os.path.basename(pdf_path.name))[0]
                out_filename = f"{base_name}.processed.pdf"
                shutil.copy2(output_path, str(results_dir / out_filename))
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

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

            summary_rows.append([
                pdf_path.name,
                job_config_obj.reference,
                shape_str or job_config_obj.shape,
                "true" if success else "false",
                message,
                str(winding_route) if winding_route is not None else "",
                "true" if layer_mismatch else ("false" if layer_mismatch is not None else ""),
                str(segment_count) if segment_count is not None else "",
            ])

        summary_csv_path = results_dir / "summary.csv"
        with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(summary_rows)

        # Save to zip_output/<zip_basename>_processed.zip
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
                    "files_processed": len(pdf_paths),
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
