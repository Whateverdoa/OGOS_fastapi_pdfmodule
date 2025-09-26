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
- Optional query params:
  - `fonts=embed|outline` (override job_config; default is embed with auto‑fallback to outline)
  - `remove_marks=true|false` (remove crop/registration marks using Separation/All)

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
  "fonts": "embed",
  "remove_marks": false
}
```

**Response:** 
- Processed PDF file download

### 3. Process PDF with JSON File
**POST** `/api/pdf/process-with-json-file`

Processes a PDF file using a separate JSON configuration file (compatible with example JSON format).

**Request:**
- `pdf_file`: PDF file upload
- `json_file`: JSON configuration file upload
- Optional query params: `fonts=embed|outline`, `remove_marks=true|false`

**Response:**
- Processed PDF file download

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
- `"circle"`: Creates circular or oval dieline (synonyms: `oval`, `ellipse`)
- `"rectangle"`: Creates rectangular dieline with optional corner radius (synonyms: `square`, `rect`)
- `"custom"`: Preserves existing dieline shape, only renames spot color (synonym: `irregular`)

### Winding Value Processing
The application includes a winding value routing system that maps winding values (1–8) to rotation angles (0°, 90°, 180°, 270°) for label processing. Mapping:

- 1 → 180°
- 2 → 0° (no rotation)
- 3 → 90°
- 4 → 270°
- 5 → 180° (inverted of 1)
- 6 → 0° (inverted of 2)
- 7 → 90° (inverted of 3)
- 8 → 270° (inverted of 4)

Winding router setup example (as configured in Esko):

![Winding router mapping example](docs/images/winding_router.png)

Note on inverted windings (5–8): these are opposite on the roll. In production, add a rewind step so orientation matches press expectations. Practically, a 90° rotation inverted on the roll corresponds to 270° after rewinding (and vice versa).

Rotation behavior:
- If the PDF trimbox size matches the job width×height (±1 mm), the base artwork is rotated according to the winding before the new dieline is overlaid (standard shapes) or before/after color renaming (custom). If winding=2, no rotation is applied.
- If sizes do not match the job JSON, rotation is skipped defensively.
- Response headers may include `X-Winding-Value`, `X-Rotation-Angle`, `X-Needs-Rotation` for traceability.

See `docs/winding_routing_specification.md` for detailed specifications.

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
│       ├── spot_color_handler.py   # Spot color manipulation
│       └── winding_router.py       # Winding value routing functions
├── docs/
│   └── winding_routing_specification.md  # Winding routing documentation
├── examplecode/                    # Example PDFs and scripts
├── main.py                         # FastAPI application
├── pyproject.toml                  # Project dependencies
└── README.md                       # This file
```

### Makefile & Scripts

Common targets:
- `make build-dev && make dev` (dev at http://localhost:8001)
- `make build && make up` (prod at http://localhost:8000)
- `make analyze PDF=path [API_BASE=url]`
- `make process PDF=path JOB_JSON='{...}' OUT=out.pdf [API_BASE]`
- `make process-json PDF=path JSON_FILE=path OUT=out.pdf [API_BASE]`
- `make check-overprint PDF=path`

Direct script usage: see `scripts/send_pdf.sh --help` (supports `--fonts embed|outline` and `--remove-marks`).

## Deployment

### Recommended: DigitalOcean App Platform
- Why: This service performs CPU-heavy PDF work and depends on Ghostscript. Serverless platforms like Vercel have strict runtime, memory, and binary limits that are not a good fit. DO App Platform (or a Droplet) runs our Docker image without those constraints.

Environments (staging → production):
- Use the same container image with different env vars.
- Staging spec: `do-app.staging.yaml` (docs enabled, DEBUG logs, higher upload limit).
- Production spec: `do-app.prod.yaml` (docs disabled, INFO logs, stricter limits).

Quick start:
- Preferred: Create an app from `do-app.staging.yaml` to test, then promote with `do-app.prod.yaml` when ready.
- Or: point DO to `Dockerfile.prod` directly and set env vars in the UI.
- Health check path: `/healthz`.
- Suggested instance: `basic-xxs` or larger depending on throughput and file sizes.

Local production run:
- `docker compose -f docker-compose.prod.yml up --build`

Key files:
- `Dockerfile.prod`: Production container (non-root, Ghostscript, Gunicorn).
- `scripts/start.sh`: Starts Gunicorn and sets sensible worker defaults.
- `gunicorn_conf.py`: Timeouts/logging tuned for heavy PDF tasks.
- `do-app.staging.yaml` / `do-app.prod.yaml`: App Platform specs for staging and prod.

### About Vercel
- Vercel excels at static sites and short-lived serverless APIs. This project needs native binaries (Ghostscript), sizeable uploads, and longer processing times. Those don’t align well with Vercel’s serverless limits. If you must use Vercel, you’d need to offload the heavy processing to a containerized worker elsewhere and only keep a thin API on Vercel.

### Env Vars of Interest
- `ENVIRONMENT` — `dev`, `staging`, or `prod`.
- `ENABLE_DOCS` — `true`/`false` to toggle FastAPI docs UI.
- `MAX_FILE_SIZE` (bytes) — reject oversized uploads.
- `LOG_LEVEL` — `INFO` (default) or `DEBUG`.
- `GUNICORN_TIMEOUT` — increase for very large PDFs (default 300s).
- `WEB_CONCURRENCY` — override worker count if needed (default 1–2 based on CPUs).

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

### Fonts Handling
- Default: embed/subset all fonts (Ghostscript). If embedding fails or any unembedded fonts are detected, the service automatically outlines text.
- Force behavior:
  - Job JSON: `"fonts": "outline"`
  - Query: `?fonts=outline`

### Registration/Crop Marks
- When enabled (`remove_marks=true` or `"remove_marks": true`), the service removes marks that use the registration color (Separation `All`), including inside Form XObjects.

### 4. Health & Version
- `GET /healthz` → `{ "status": "ok", "uptime_seconds": <float> }`
- `GET /version` → `{ "name", "version", "git_commit" }`

Tip: set `GIT_COMMIT` env var during deploy to report the commit.

### Overprint
- Dielines are enforced with overprint in the overlay form stream so output RIPs honor overprint on the spot stroke.

## Known Limitations

1. **Custom Shape Processing**: Currently copies the PDF without full spot color renaming (placeholder implementation)
2. **Multi-page PDFs**: Optimized for single-page label PDFs
3. **Complex Paths**: May not detect all types of complex dieline paths

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
