import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.pdf_analyzer import PDFAnalyzer
from app.core.pdf_processor import PDFProcessor
from main import app


def _build_blank_pdf(target: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with target.open("wb") as handle:
        writer.write(handle)


def _sample_analysis() -> dict:
    return {
        "pdf_size": {"width": 100.0, "height": 100.0},
        "page_count": 1,
        "trimbox": None,
        "mediabox": {"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
        "detected_dielines": [],
        "dieline_layers": {
            "layer_mismatch": True,
            "segments": [
                {
                    "layer": "OC1 /stans",
                    "stroke_color": [0.0, 1.0, 0.0, 0.0],
                    "line_width": 0.5,
                    "bounding_box": {"x0": 5.0, "y0": 5.0, "x1": 90.0, "y1": 90.0},
                },
                {
                    "layer": "OC2 CutContour",
                    "stroke_color": [0.0, 1.0, 0.0, 0.0],
                    "line_width": 0.5,
                    "bounding_box": {"x0": 10.0, "y0": 10.0, "x1": 80.0, "y1": 80.0},
                },
            ],
        },
        "spot_colors": ["stans"],
        "has_cutcontour": True,
    }


def test_analyze_returns_dieline_layers(monkeypatch, tmp_path):
    client = TestClient(app)
    pdf_path = tmp_path / "input.pdf"
    _build_blank_pdf(pdf_path)

    analysis_payload = _sample_analysis()

    monkeypatch.setattr(PDFAnalyzer, "analyze_pdf", lambda self, _: analysis_payload)

    with pdf_path.open("rb") as handle:
        response = client.post(
            "/api/pdf/analyze",
            files={"pdf_file": ("input.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["dieline_layers"]["layer_mismatch"] is True
    assert len(body["dieline_layers"]["segments"]) == 2
    for segment in body["dieline_layers"]["segments"]:
        assert "bounding_box" in segment


def test_process_json_includes_analysis_and_pdf(monkeypatch, tmp_path):
    client = TestClient(app)
    pdf_path = tmp_path / "input.pdf"
    _build_blank_pdf(pdf_path)

    output_path = tmp_path / "output.pdf"
    processed_payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF"
    analysis_payload = _sample_analysis()

    def _fake_process(self, input_path, job_config):
        with output_path.open("wb") as handle:
            handle.write(processed_payload)
        return {
            "success": True,
            "message": "ok",
            "reference": job_config.reference,
            "output_path": str(output_path),
            "analysis": analysis_payload,
            "processing_details": {"winding_route": 90},
        }

    monkeypatch.setattr(PDFProcessor, "process_pdf", _fake_process)

    job_config = {
        "reference": "TEST-123",
        "shape": "circle",
        "width": 50,
        "height": 50,
        "line_thickness": 0.5,
        "spot_color_name": "stans",
    }

    with pdf_path.open("rb") as handle:
        response = client.post(
            "/api/pdf/process",
            params={"return_json": "true"},
            data={"job_config": json.dumps(job_config)},
            files={"pdf_file": ("input.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["dieline_layers"]["layer_mismatch"] is True
    encoded = body["processed_pdf_base64"]
    assert encoded
    assert base64.b64decode(encoded) == processed_payload


def test_process_file_response_sets_layer_headers(monkeypatch, tmp_path):
    client = TestClient(app)
    pdf_path = tmp_path / "input.pdf"
    _build_blank_pdf(pdf_path)

    output_path = tmp_path / "output.pdf"
    processed_payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF"
    analysis_payload = _sample_analysis()

    def _fake_process(self, input_path, job_config):
        with output_path.open("wb") as handle:
            handle.write(processed_payload)
        return {
            "success": True,
            "message": "ok",
            "reference": job_config.reference,
            "output_path": str(output_path),
            "analysis": analysis_payload,
            "processing_details": {"winding_route": 90},
        }

    monkeypatch.setattr(PDFProcessor, "process_pdf", _fake_process)

    job_config = {
        "reference": "TEST-123",
        "shape": "circle",
        "width": 50,
        "height": 50,
        "line_thickness": 0.5,
        "spot_color_name": "stans",
    }

    with pdf_path.open("rb") as handle:
        response = client.post(
            "/api/pdf/process",
            data={"job_config": json.dumps(job_config)},
            files={"pdf_file": ("input.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 200
    assert response.headers["x-dieline-layer-mismatch"] == "true"
    assert response.headers["x-dieline-segment-count"] == "2"
    assert response.headers["x-processing-reference"] == "TEST-123"
