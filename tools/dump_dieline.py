"""CLI helper to inspect dieline layer diagnostics for a PDF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.pdf_analyzer import PDFAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to the PDF to inspect")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only the dieline layer report as JSON",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=None,
        help="Pretty-print JSON output with the given indentation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.pdf.exists():
        print(f"Error: {args.pdf} does not exist", file=sys.stderr)
        sys.exit(1)

    analyzer = PDFAnalyzer()
    analysis = analyzer.analyze_pdf(str(args.pdf))
    dieline_layers = analysis.get("dieline_layers", {}) or {}
    segments = dieline_layers.get("segments") or []
    mismatch = bool(dieline_layers.get("layer_mismatch"))

    if args.json:
        print(json.dumps(dieline_layers, indent=args.indent))
        return

    layer_status = "YES" if mismatch else "no"
    print(f"Layer mismatch: {layer_status}")
    print(f"Segments detected: {len(segments)}")

    for index, segment in enumerate(segments, start=1):
        layer = segment.get("layer", "<unknown>")
        width = segment.get("line_width")
        bbox = segment.get("bounding_box") or {}
        colour = segment.get("stroke_color")

        print(f"Segment {index}: layer={layer}")
        if width is not None:
            print(f"  line_width_mm={width}")
        if colour:
            print(f"  stroke_color={colour}")
        if bbox:
            print(
                "  bbox_mm=(x0={x0}, y0={y0}, x1={x1}, y1={y1})".format(
                    x0=bbox.get("x0"),
                    y0=bbox.get("y0"),
                    x1=bbox.get("x1"),
                    y1=bbox.get("y1"),
                )
            )


if __name__ == "__main__":
    main()
