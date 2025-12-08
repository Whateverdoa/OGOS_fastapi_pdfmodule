#!/usr/bin/env python3
"""
Test script to verify q/Q graphics state balance fix.

This script:
1. Validates q/Q balance in input PDFs
2. Processes them through the pipeline
3. Validates q/Q balance in output PDFs
4. Reports any issues

Usage:
    python test_qQ_balance.py [pdf_path]
    
If no PDF path is provided, it will scan pdf_storage/original/ for test files.
"""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.graphics_state_validator import GraphicsStateValidator, PDFValidationResult
from app.core.pdf_processor import PDFProcessor
from app.models.schemas import PDFJobConfig, ShapeType


def print_validation_result(result: PDFValidationResult, label: str):
    """Pretty print validation results."""
    status = "✅ BALANCED" if result.is_valid else "❌ IMBALANCED"
    print(f"\n{label}: {status}")
    print(f"  Total streams: {result.total_streams}")
    print(f"  Imbalanced streams: {result.imbalanced_streams}")
    
    if result.error:
        print(f"  Error: {result.error}")
    
    if not result.is_valid:
        for sr in result.stream_results:
            if not sr.is_balanced:
                print(f"  - Stream {sr.xref}: q={sr.q_count}, Q={sr.Q_count}, excess_Q={sr.excess_Q}")


def test_single_pdf(pdf_path: str, validator: GraphicsStateValidator):
    """Test a single PDF file."""
    print(f"\n{'='*60}")
    print(f"Testing: {pdf_path}")
    print('='*60)
    
    if not os.path.exists(pdf_path):
        print(f"  ❌ File not found: {pdf_path}")
        return False
    
    # Step 1: Validate input PDF
    print("\n[Step 1] Validating input PDF...")
    input_result = validator.validate_pdf(pdf_path)
    print_validation_result(input_result, "Input PDF")
    
    # Step 2: Process through pipeline
    print("\n[Step 2] Processing through PDF pipeline...")
    processor = PDFProcessor()
    
    # Create a test job config
    job_config = PDFJobConfig(
        reference="test_qQ_balance",
        width=100.0,
        height=100.0,
        shape=ShapeType.custom,  # Keep existing shape
        spot_color_name="stans",
        line_thickness=0.5,
    )
    
    # Create temp output
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        output_path = tmp.name
    
    try:
        result = processor.process_pdf(pdf_path, job_config)
        
        if not result.get('success'):
            print(f"  ❌ Processing failed: {result.get('error', result.get('message'))}")
            return False
        
        actual_output = result.get('output_path', output_path)
        print(f"  ✅ Processing succeeded")
        print(f"  Output: {actual_output}")
        
        # Step 3: Validate output PDF
        print("\n[Step 3] Validating output PDF...")
        output_result = validator.validate_pdf(actual_output)
        print_validation_result(output_result, "Output PDF")
        
        # Step 4: Summary
        print("\n[Summary]")
        if output_result.is_valid:
            print("  ✅ SUCCESS: Output PDF has balanced q/Q operators")
            print("  This PDF should work correctly in iText7/C#")
            return True
        else:
            print("  ❌ FAILURE: Output PDF still has imbalanced q/Q operators")
            print("  This PDF may cause 'Stack empty' errors in iText7")
            
            # Try to fix it
            print("\n[Step 4] Attempting auto-fix...")
            fix_result = validator.validate_and_fix_pdf(actual_output)
            print_validation_result(fix_result, "After auto-fix")
            
            return fix_result.is_valid
            
    except Exception as e:
        print(f"  ❌ Exception during processing: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except:
                pass


def find_test_pdfs(base_dir: str, limit: int = 5) -> list:
    """Find PDF files to test."""
    pdfs = []
    
    # Check pdf_storage/original/
    original_dir = os.path.join(base_dir, 'pdf_storage', 'original')
    if os.path.exists(original_dir):
        for f in os.listdir(original_dir):
            if f.lower().endswith('.pdf'):
                pdfs.append(os.path.join(original_dir, f))
                if len(pdfs) >= limit:
                    break
    
    # Check examplecode/ subdirectories
    if len(pdfs) < limit:
        example_dir = os.path.join(base_dir, 'examplecode')
        if os.path.exists(example_dir):
            for subdir in os.listdir(example_dir):
                subpath = os.path.join(example_dir, subdir)
                if os.path.isdir(subpath):
                    for f in os.listdir(subpath):
                        if f.lower().endswith('.pdf'):
                            pdfs.append(os.path.join(subpath, f))
                            if len(pdfs) >= limit:
                                break
                if len(pdfs) >= limit:
                    break
    
    return pdfs


def main():
    """Main entry point."""
    print("=" * 60)
    print("q/Q Graphics State Balance Test")
    print("=" * 60)
    
    validator = GraphicsStateValidator(debug=False)
    base_dir = Path(__file__).parent
    
    # Get PDFs to test
    if len(sys.argv) > 1:
        # Test specific PDF(s) provided as arguments
        test_pdfs = sys.argv[1:]
    else:
        # Find some test PDFs
        print("\nNo PDF specified, scanning for test files...")
        test_pdfs = find_test_pdfs(str(base_dir), limit=3)
        
        if not test_pdfs:
            print("❌ No PDF files found to test!")
            print("\nUsage: python test_qQ_balance.py <pdf_path>")
            sys.exit(1)
        
        print(f"Found {len(test_pdfs)} PDF(s) to test")
    
    # Run tests
    results = []
    for pdf_path in test_pdfs:
        success = test_single_pdf(pdf_path, validator)
        results.append((pdf_path, success))
    
    # Final summary
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    passed = sum(1 for _, s in results if s)
    failed = len(results) - passed
    
    for pdf_path, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {os.path.basename(pdf_path)}")
    
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)}")
    
    if failed > 0:
        sys.exit(1)
    
    print("\n✅ All tests passed! The q/Q balance fix is working correctly.")


if __name__ == "__main__":
    main()


