# FastAPI PDF Dieline Processor

A FastAPI service for processing PDF files with dielines/stanslines. The service can detect existing dielines, analyze PDF properties, and modify or replace dielines based on shape specifications.

## Features

- **PDF Analysis**: Extract dimensions, trimbox, and detect existing dielines
- **Shape Support**: 
  - Circle/Oval
  - Rectangle (with optional corner radius)
  - Custom/Irregular shapes
- **Spot Color Handling**: Detect and manipulate spot colors (CutContour, KissCut, stans, etc.)
- **Dieline Processing**:
  - For circles/rectangles: Remove existing dieline and add new one
  - For custom shapes: Keep existing shape but rename spot color
- **Standards Compliant**: Creates dielines with 0.5pt 100% magenta lines with overprint

## Installation

### Prerequisites
- Python 3.10+
- UV package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd OGOS_fastapi_pdfmodule
```

2. Install dependencies using UV:
```bash
uv sync
```

3. Run the development server:
```bash
uv run uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### 1. Analyze PDF
**POST** `/api/pdf/analyze`

Analyzes a PDF file and returns information about its dimensions, trimbox, and detected dielines.

**Request:**
- Form data with PDF file upload

**Response:**
```json
{
  "pdf_size": {"width": 595.0, "height": 842.0},
  "page_count": 1,
  "trimbox": {"x0": 0, "y0": 0, "x1": 595, "y1": 842},
  "mediabox": {"x0": 0, "y0": 0, "x1": 595, "y1": 842},
  "detected_dielines": [...],
  "spot_colors": ["CutContour"],
  "has_cutcontour": true
}
```

### 2. Process PDF
**POST** `/api/pdf/process`

Processes a PDF file with dieline modifications based on job configuration.

**Request:**
- `pdf_file`: PDF file upload
- `job_config`: JSON string with configuration

**Example job_config:**
```json
{
  "reference": "5355531-8352950",
  "shape": "circle",
  "width": 50,
  "height": 50,
  "radius": 0,
  "spot_color_name": "stans",
  "line_thickness": 0.5,
  "winding": 2
}
```

**Response:** 
- Processed PDF file download

Response headers include:
- `X-Processing-Reference`
- `X-Processing-Shape`
- `X-Winding-Route` (if `winding` supplied)

Winding route mapping is automatically computed from `winding` using:
1 → 180, 2 → 0, 3 → 90, 4 → 270, 5/6/7/8 → 0.

Example curl (inline JSON):
```bash
curl -X POST http://localhost:8000/api/pdf/process \
  -F "pdf_file=@/path/to/file.pdf" \
  -F 'job_config={
    "reference":"PROD-12345",
    "shape":"circle",
    "width":50,
    "height":50,
    "spot_color_name":"stans",
    "line_thickness":0.5,
    "winding":2
  }' \
  -D - \
  -o PROD-12345_processed.pdf
# Look for X-Winding-Route in response headers
```

### 3. Process PDF with JSON File
**POST** `/api/pdf/process-with-json-file`

Processes a PDF file using a separate JSON configuration file (compatible with example JSON format).

**Request:**
- `pdf_file`: PDF file upload
- `json_file`: JSON configuration file upload

**Response:**
- Processed PDF file download

Example JSON file content:
```json
{
  "ReferenceAtCustomer": "PROD-67890",
  "Description": "40x140mm rectangle, 2mm radius",
  "Shape": "rectangle",
  "Width": 40,
  "Height": 140,
  "Radius": 2,
  "Winding": 3,
  "Substrate": "PP white",
  "Adhesive": "permanent",
  "Colors": "CMYK"
}
```

Example curl (separate JSON file):
```bash
curl -X POST http://localhost:8000/api/pdf/process-with-json-file \
  -F "pdf_file=@/path/to/file.pdf" \
  -F "json_file=@/path/to/config.json" \
  -D - \
  -o PROD-67890_processed.pdf
# Look for X-Winding-Route in response headers
```

### 4. Winding Route
**GET** `/api/pdf/route-by-winding/{winding_value}`

Returns the mapped route angle (0, 90, 180, 270) for a given winding value (1-8). Accepts string or numeric input.

Example:
```bash
curl -s http://localhost:8000/api/pdf/route-by-winding/3
# {"winding_value":"3","route":90}
```

## Configuration

The application can be configured using environment variables or a `.env` file:

```env
API_TITLE=PDF Dieline Processor
API_VERSION=1.0.0
MAX_FILE_SIZE=104857600  # 100MB in bytes
DEFAULT_SPOT_COLOR=stans
DEFAULT_LINE_THICKNESS=0.5
LOG_LEVEL=INFO
```

## JSON Configuration Format

The service accepts JSON configuration in the following format:

```json
{
  "ReferenceAtCustomer": "5355531-8352950",
  "Description": "labels_on_roll",
  "Shape": "circle",
  "Width": 50,
  "Height": 50,
  "Radius": 0,
  "Substrate": "mat wit PP",
  "Adhesive": "permanent",
  "Colors": "CMYK",
  "Winding": 2
}
```

### Shape Types
- `"circle"`: Creates circular or oval dieline
- `"rectangle"`: Creates rectangular dieline with optional corner radius
- `"custom"`: Preserves existing dieline shape, only renames spot color

## Development

### Project Structure
```
OGOS_fastapi_pdfmodule/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       └── pdf.py              # API endpoints
│   ├── core/
│   │   ├── config.py               # Configuration
│   │   ├── pdf_analyzer.py         # PDF analysis
│   │   ├── pdf_processor.py        # Main processing logic
│   │   └── shape_generators.py     # Shape generation
│   ├── models/
│   │   └── schemas.py              # Pydantic models
│   └── utils/
│       ├── pdf_utils.py            # PDF utilities
│       └── spot_color_handler.py   # Spot color manipulation
├── examplecode/                    # Example PDFs and scripts
├── main.py                         # FastAPI application
├── pyproject.toml                  # Project dependencies
└── README.md                       # This file
```

### Testing

Test the API using the provided HTTP file:

```bash
# Run the server
uv run uvicorn main:app --reload

# Test endpoints using test_main.http
```

Or use curl:

```bash
# Analyze a PDF
curl -X POST "http://localhost:8000/api/pdf/analyze" \
  -H "accept: application/json" \
  -F "pdf_file=@example.pdf"

# Process a PDF
curl -X POST "http://localhost:8000/api/pdf/process" \
  -H "accept: application/pdf" \
  -F "pdf_file=@example.pdf" \
  -F 'job_config={"reference":"test-001","shape":"circle","width":50,"height":50}'
```

## Technical Details

### Dieline Detection
The service detects dielines by looking for:
- Spot colors named: CutContour, KissCut, stans, DieCut (and variations)
- Thin stroke-only paths (≤1.0pt line width)
- Paths without fill color

### PDF Processing
- Uses **PyMuPDF** for PDF analysis and path extraction
- Uses **pypdf** for spot color detection
- Uses **ReportLab** for generating new dieline shapes
- Preserves original PDF content while modifying only dieline elements

### Spot Color Specification
All dielines are created with:
- 100% Magenta (CMYK: 0, 1, 0, 0)
- 0.5pt line thickness (configurable)
- Overprint enabled
- Custom spot color name (default: "stans")

## Known Limitations

1. **Custom Shape Processing**: Currently copies the PDF without full spot color renaming (placeholder implementation)
2. **Multi-page PDFs**: Optimized for single-page label PDFs
3. **Complex Paths**: May not detect all types of complex dieline paths

## Field Usage Notes

- `winding`: Used to compute and return a route angle via header `X-Winding-Route` and in the JSON `processing_details` of the internal result. Currently not rotating or altering the artwork; it’s metadata for downstream handling.
- `substrate` / `adhesive` / `colors`: Accepted and preserved in the job config, but not used to alter processing at this time. If you need behavior based on a substrate ID (e.g., different line thickness or color), we can add a rule table.

## Future Enhancements

- [ ] Full implementation of spot color renaming for custom shapes
- [ ] Support for multi-page PDF processing
- [ ] Batch processing API endpoint
- [ ] Advanced dieline detection algorithms
- [ ] WebSocket support for real-time processing status

## License

[Your License Here]

## Support

For issues or questions, please contact [Your Contact Info]
