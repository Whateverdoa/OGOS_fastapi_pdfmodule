from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ShapeType(str, Enum):
    circle = "circle"
    rectangle = "rectangle"
    custom = "custom"


class PDFJobConfig(BaseModel):
    """Configuration for PDF processing job based on JSON input"""
    reference: str = Field(..., description="Reference number from customer")
    description: Optional[str] = Field(None, description="Job description")
    shape: ShapeType = Field(..., description="Shape type: circle, rectangle, or custom")
    width: float = Field(..., description="Width in millimeters")
    height: float = Field(..., description="Height in millimeters")
    radius: Optional[float] = Field(0, description="Corner radius for rectangle in millimeters")
    spot_color_name: str = Field("stans", description="Name for the spot color")
    line_thickness: float = Field(0.5, description="Line thickness in points")
    winding: Optional[int] = Field(None, description="Winding direction")
    substrate: Optional[str] = Field(None, description="Substrate material")
    adhesive: Optional[str] = Field(None, description="Adhesive type")
    colors: Optional[str] = Field(None, description="Color specification")
    rotate_degrees: Optional[int] = Field(
        None,
        description="Page rotation to apply before processing (degrees: 0, 90, 180, 270)"
    )


class DielineBoundingBox(BaseModel):
    """Axis-aligned bounding box expressed in millimetres."""

    x0: float = Field(..., description="Lower-left x coordinate in millimetres")
    y0: float = Field(..., description="Lower-left y coordinate in millimetres")
    x1: float = Field(..., description="Upper-right x coordinate in millimetres")
    y1: float = Field(..., description="Upper-right y coordinate in millimetres")


class DielineLayerSegment(BaseModel):
    """Describes a single stroked dieline segment detected on the page."""

    layer: str = Field(..., description="Original layer/OCG name reported by the PDF")
    stroke_color: Optional[List[float]] = Field(
        None,
        description="Stroke colour components as reported by PyMuPDF (device colour space)"
    )
    line_width: Optional[float] = Field(
        None,
        description="Stroke width in millimetres when available"
    )
    bounding_box: Optional[DielineBoundingBox] = Field(
        None,
        description="Bounding box of the stroked geometry in millimetres"
    )


class DielineLayerReport(BaseModel):
    """Aggregated layer information for dieline strokes."""

    segments: List[DielineLayerSegment] = Field(
        default_factory=list,
        description="Ordered segments that contributed to the dieline layer analysis"
    )
    layer_mismatch: bool = Field(
        False,
        description="True when dieline strokes span multiple canonical layers/aliases"
    )


class PDFAnalysisResult(BaseModel):
    """Result of PDF analysis"""

    pdf_size: Dict[str, float] = Field(..., description="PDF dimensions in millimeters (width, height)")
    page_count: int = Field(..., description="Number of pages in PDF")
    trimbox: Optional[Dict[str, float]] = Field(None, description="Trimbox coordinates in millimeters (x0, y0, x1, y1)")
    mediabox: Dict[str, float] = Field(..., description="Mediabox coordinates in millimeters (x0, y0, x1, y1)")
    detected_dielines: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detected dieline information with dimensions in mm"
    )
    dieline_layers: DielineLayerReport = Field(
        default_factory=DielineLayerReport,
        description="Detailed layer-level reporting for dieline segments"
    )
    spot_colors: List[str] = Field(default_factory=list, description="List of spot colors found")
    has_cutcontour: bool = Field(False, description="Whether CutContour or similar was detected")


class PDFProcessingRequest(BaseModel):
    """Request for PDF processing"""
    job_config: PDFJobConfig = Field(..., description="Job configuration from JSON")


class PDFProcessingResponse(BaseModel):
    """Response from PDF processing"""
    success: bool = Field(..., description="Whether processing was successful")
    message: str = Field(..., description="Status message")
    reference: str = Field(..., description="Reference number")
    analysis: Optional[PDFAnalysisResult] = Field(None, description="PDF analysis results")
    processing_details: Optional[Dict[str, Any]] = Field(None, description="Details about the processing")
    processed_pdf_base64: Optional[str] = Field(
        None,
        description="Base64-encoded processed PDF returned when JSON responses are requested"
    )


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    reference: Optional[str] = Field(None, description="Reference number if available")


class WindingRouteResponse(BaseModel):
    """Response for winding routing endpoint"""
    winding_value: str = Field(..., description="Original input winding value")
    route: int = Field(..., description="Mapped route angle (0, 90, 180, 270)")
