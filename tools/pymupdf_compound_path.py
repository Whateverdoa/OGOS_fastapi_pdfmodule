"""CLI utility to normalise dieline compound paths using PyMuPDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.utils.pymupdf_compound_path_tool import PyMuPDFCompoundPathTool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input PDF path")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tool = PyMuPDFCompoundPathTool()
    result = tool.process(str(args.input), str(args.output) if args.output else None)

    if result.xrefs_processed:
        print("Updated xref streams:", ", ".join(map(str, result.xrefs_processed)))
        print(f"Removed {result.sequences_removed} sequences across {result.sequences_combined} compound paths")
    else:
        print("No stans sequences required merging – PDF left unchanged")


if __name__ == "__main__":
    main()
