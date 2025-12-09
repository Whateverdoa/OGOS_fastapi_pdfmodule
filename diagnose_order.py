#!/usr/bin/env python3
"""
CLI tool to diagnose winding issues for a specific order.

Usage:
    python diagnose_order.py 6001949316-2
    python diagnose_order.py 6001949316-2 --verbose
"""

import sys
import json
import argparse
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.winding_diagnostics import WindingDiagnostics


def format_diagnostics(diagnostics: dict, verbose: bool = False) -> str:
    """Format diagnostics output for display"""
    lines = []
    
    # Input section
    lines.append("=" * 60)
    lines.append("INPUT")
    lines.append("=" * 60)
    input_data = diagnostics.get("input", {})
    lines.append(f"  Winding: {input_data.get('winding')} (type: {input_data.get('winding_type')})")
    lines.append(f"  Width: {input_data.get('width')}")
    lines.append(f"  Height: {input_data.get('height')}")
    
    # Processing section
    lines.append("\n" + "=" * 60)
    lines.append("PROCESSING")
    lines.append("=" * 60)
    processing = diagnostics.get("processing", {})
    rotation = processing.get("rotation_angle")
    if rotation is not None:
        lines.append(f"  Parsed Winding: {processing.get('parsed_winding')}")
        lines.append(f"  Rotation Angle: {rotation}°")
        lines.append(f"  Needs Rotation: {processing.get('needs_rotation')}")
        lines.append(f"  Should Swap Dimensions: {processing.get('should_swap_dimensions')}")
    else:
        lines.append("  ⚠️  Could not determine rotation angle")
    
    # Output section
    lines.append("\n" + "=" * 60)
    lines.append("OUTPUT")
    lines.append("=" * 60)
    output = diagnostics.get("output", {})
    lines.append(f"  Normalized Winding: {output.get('normalized_winding')}")
    if output.get("winding_changed"):
        lines.append("  ⚠️  Winding was changed during normalization")
    
    # Dimensions section
    dims = diagnostics.get("dimensions", {})
    if dims:
        lines.append("\n" + "=" * 60)
        lines.append("DIMENSIONS")
        lines.append("=" * 60)
        input_dims = dims.get("input", {})
        lines.append(f"  Input: {input_dims.get('width')} × {input_dims.get('height')}")
        
        expected_swap = dims.get("expected_downstream_swap")
        if expected_swap:
            expected = dims.get("expected_final", {})
            lines.append(f"  ⚠️  Expected downstream swap: {expected.get('width')} × {expected.get('height')}")
        else:
            lines.append("  ✓ No dimension swap expected downstream")
    
    # Errors section
    errors = diagnostics.get("errors", [])
    if errors:
        lines.append("\n" + "=" * 60)
        lines.append("ERRORS")
        lines.append("=" * 60)
        for error in errors:
            lines.append(f"  ❌ {error}")
    
    # Verbose JSON output
    if verbose:
        lines.append("\n" + "=" * 60)
        lines.append("RAW JSON")
        lines.append("=" * 60)
        lines.append(json.dumps(diagnostics, indent=2))
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose winding issues for a specific order"
    )
    parser.add_argument(
        "order_reference",
        help="Order reference (e.g., 6001949316-2)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose JSON output"
    )
    
    args = parser.parse_args()
    
    print(f"Diagnosing order: {args.order_reference}\n")
    
    diagnostics = WindingDiagnostics()
    report = diagnostics.analyze_order(args.order_reference)
    
    # Show file information
    print("=" * 60)
    print("FILES FOUND")
    print("=" * 60)
    files = report["files"]
    
    if files["original_files"]:
        print(f"\nOriginal Files ({len(files['original_files'])}):")
        for f in files["original_files"]:
            print(f"  - {f['name']} ({f['size']} bytes)")
    
    if files["processed_files"]:
        print(f"\nProcessed Files ({len(files['processed_files'])}):")
        for f in files["processed_files"]:
            print(f"  - {f['name']} ({f['size']} bytes)")
    
    if files["json_files"]:
        print(f"\nJSON Files ({len(files['json_files'])}):")
        for json_file in files["json_files"]:
            print(f"  - {json_file['name']}")
            if "winding" in json_file:
                print(f"    Winding: {json_file['winding']}")
            if "width" in json_file and "height" in json_file:
                print(f"    Dimensions: {json_file['width']} × {json_file['height']}")
    else:
        print("\n⚠️  No JSON files found")
    
    # Show analysis
    analysis = report["analysis"]
    if analysis:
        print("\n" + "=" * 60)
        print("WINDING FLOW ANALYSIS")
        print("=" * 60)
        for json_name, diag in analysis.items():
            print(f"\n📄 {json_name}")
            print(format_diagnostics(diag, verbose=args.verbose))
    else:
        print("\n⚠️  No analysis available (no JSON files with data found)")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if not files["found"]:
        print("❌ No files found for this order reference")
        sys.exit(1)
    elif not files["json_files"]:
        print("⚠️  Files found but no JSON configuration files")
        print("   This makes it difficult to trace winding values")
    else:
        print("✓ Analysis complete")
        # Check for potential issues
        for json_name, diag in analysis.items():
            errors = diag.get("errors", [])
            if errors:
                print(f"\n⚠️  Issues found in {json_name}:")
                for error in errors:
                    print(f"   - {error}")


if __name__ == "__main__":
    main()

