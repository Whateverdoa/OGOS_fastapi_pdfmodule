from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import json
import os
import tempfile
import shutil
from ...models.schemas import (
    PDFJobConfig, PDFAnalysisResult, PDFProcessingResponse,
    ErrorResponse, ShapeType, WindingRouteResponse
)
from ...core.pdf_processor import PDFProcessor
from ...core.pdf_analyzer import PDFAnalyzer
from ...core.config import settings
from ...utils.winding_router import route_by_winding_str


router = APIRouter(prefix="/api/pdf", tags=["pdf"])


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
    job_config: str = Form(...)
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
        job_config_obj = PDFJobConfig(**config_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in job_config: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid job configuration: {str(e)}")
        
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
            winding_route = (
                result.get('processing_details', {}).get('winding_route')
                if isinstance(result.get('processing_details'), dict) else None
            )
            if winding_route is not None:
                headers['X-Winding-Route'] = str(winding_route)

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
    json_file: UploadFile = File(...)
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
        # Handle both uppercase and lowercase shape values
        shape_value = config_dict.get('Shape', config_dict.get('shape', '')).lower()
        
        job_config_data = {
            'reference': config_dict.get('ReferenceAtCustomer', config_dict.get('reference', '')),
            'description': config_dict.get('Description', ''),
            'shape': shape_value,
            'width': float(config_dict.get('Width', config_dict.get('width', 0))),
            'height': float(config_dict.get('Height', config_dict.get('height', 0))),
            'radius': float(config_dict.get('Radius', config_dict.get('radius', 0))),
            'winding': config_dict.get('Winding', config_dict.get('winding')),
            'substrate': config_dict.get('Substrate', config_dict.get('substrate')),
            'adhesive': config_dict.get('Adhesive', config_dict.get('adhesive')),
            'colors': config_dict.get('Colors', config_dict.get('colors'))
        }
        
        job_config_obj = PDFJobConfig(**job_config_data)
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing configuration: {str(e)}")
        
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
            winding_route = (
                result.get('processing_details', {}).get('winding_route')
                if isinstance(result.get('processing_details'), dict) else None
            )
            if winding_route is not None:
                headers['X-Winding-Route'] = str(winding_route)

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
