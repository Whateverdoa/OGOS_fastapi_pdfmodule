#!/usr/bin/env python3
"""
Extract PDF from failed JSON file and check for q/Q errors.

Usage:
    python check_failed_pdf.py <json_path>
"""
import base64
import json
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.graphics_state_validator import GraphicsStateValidator, PDFValidationResult


def extract_pdf_from_json(json_path: str, output_path: str = None) -> str:
    """
    Extract PDF from JSON file and save to file.
    
    Args:
        json_path: Path to JSON file
        output_path: Optional output path. If None, saves next to JSON file.
    
    Returns:
        Path to saved PDF file
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find PDF in Lines
    pdf_base64 = None
    if 'Lines' in data and len(data['Lines']) > 0:
        for line in data['Lines']:
            if 'PdfFile' in line:
                pdf_base64 = line['PdfFile']
                break
    
    if not pdf_base64:
        raise ValueError("No PdfFile found in JSON")
    
    # Decode base64
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 PDF: {e}")
    
    # Determine output path
    if output_path is None:
        json_file = Path(json_path)
        output_path = json_file.parent / f"{json_file.stem}_extracted.pdf"
    
    # Save PDF
    with open(output_path, 'wb') as f:
        f.write(pdf_bytes)
    
    return str(output_path)


def print_validation_result(result: PDFValidationResult, label: str):
    """Pretty print validation results."""
    status = "✅ BALANCED" if result.is_valid else "❌ IMBALANCED"
    print(f"\n{label}: {status}")
    print(f"  Total streams: {result.total_streams}")
    print(f"  Imbalanced streams: {result.imbalanced_streams}")
    
    if result.error:
        print(f"  Error: {result.error}")
    
    if not result.is_valid:
        print("\n  Imbalanced streams details:")
        for sr in result.stream_results:
            if not sr.is_balanced:
                print(f"    - Stream {sr.xref}: q={sr.q_count}, Q={sr.Q_count}, excess_Q={sr.excess_Q}")
                if sr.excess_Q > 0:
                    print(f"      ⚠️  More Q than q - will cause stack underflow!")
                else:
                    print(f"      ⚠️  More q than Q - will cause stack overflow!")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python check_failed_pdf.py <json_path>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    
    print("=" * 60)
    print(f"Checking PDF from: {json_path}")
    print("=" * 60)
    
    pdf_path = None
    try:
        # Extract PDF from JSON
        print("\n[Step 1] Extracting PDF from JSON...")
        pdf_path = extract_pdf_from_json(json_path)
        print(f"  ✅ PDF extracted to: {pdf_path}")
        
        # Validate q/Q balance
        print("\n[Step 2] Checking q/Q balance...")
        validator = GraphicsStateValidator(debug=True)
        result = validator.validate_pdf(pdf_path)
        print_validation_result(result, "PDF Validation")
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if result.is_valid:
            print("✅ PDF has balanced q/Q operators")
            print("   This PDF should work correctly in iText7/C#")
        else:
            print("❌ PDF has imbalanced q/Q operators")
            print("   This PDF may cause 'Stack empty' errors in iText7")
            print("\n   Consider using validator.validate_and_fix_pdf() to auto-fix")
        
        print(f"\n📄 PDF saved at: {pdf_path}")
        print("   You can now view this file in your PDF viewer")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

