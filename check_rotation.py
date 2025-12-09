#!/usr/bin/env python3
"""
Check if a PDF was rotated during processing.

This script analyzes a PDF file to determine:
1. Current page rotation value
2. Whether rotation was applied
3. Expected rotation based on winding value

Usage:
    python check_rotation.py <pdf_path> [winding_value]
    
Example:
    python check_rotation.py pdf_storage/processed/20251208_114356_6001949316-1_design_1_processed_6001949316-1.pdf 4
"""

import sys
from pathlib import Path
import fitz  # PyMuPDF

def check_pdf_rotation(pdf_path: str, expected_winding: int = None):
    """Check rotation status of a PDF file."""
    print('=' * 70)
    print('PDF ROTATION CHECK')
    print('=' * 70)
    print()
    
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        return
    
    try:
        doc = fitz.open(pdf_path)
        
        print(f"📄 File: {Path(pdf_path).name}")
        print(f"   Pages: {len(doc)}")
        print()
        
        # Check rotation for each page
        rotations = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            rotation = page.rotation
            rotations.append(rotation)
            
            print(f"📄 Page {page_num + 1}:")
            print(f"   Rotation: {rotation}°")
            
            # Get page dimensions
            rect = page.rect
            mediabox = page.mediabox
            print(f"   Page Rect: {rect.width:.2f} × {rect.height:.2f} points")
            print(f"   MediaBox: {mediabox.width:.2f} × {mediabox.height:.2f} points")
            print()
        
        # Summary
        unique_rotations = set(rotations)
        if len(unique_rotations) == 1:
            rotation_value = rotations[0]
            print('=' * 70)
            print('SUMMARY')
            print('=' * 70)
            print(f"All pages have rotation: {rotation_value}°")
            
            if rotation_value == 0:
                print("✅ No rotation applied (0°)")
            elif rotation_value in (90, 180, 270):
                print(f"✅ PDF is rotated {rotation_value}°")
            else:
                print(f"⚠️  Unexpected rotation value: {rotation_value}°")
            
            # Check against expected winding
            if expected_winding is not None:
                print()
                print('=' * 70)
                print('WINDING VERIFICATION')
                print('=' * 70)
                
                # Winding to rotation mapping
                winding_map = {
                    1: 180,
                    2: 0,
                    3: 90,
                    4: 270,
                    5: 180,
                    6: 0,
                    7: 90,
                    8: 270,
                }
                
                expected_rotation = winding_map.get(expected_winding)
                if expected_rotation is not None:
                    print(f"Expected Winding: {expected_winding}")
                    print(f"Expected Rotation: {expected_rotation}°")
                    print(f"Actual Rotation: {rotation_value}°")
                    
                    if rotation_value == expected_rotation:
                        print("✅ MATCH: Rotation matches expected winding value")
                    else:
                        print(f"❌ MISMATCH: Expected {expected_rotation}°, got {rotation_value}°")
                        if expected_rotation == 0 and rotation_value != 0:
                            print("   ⚠️  Winding 2 should have 0° rotation (no rotation)")
                        elif expected_rotation != 0 and rotation_value == 0:
                            print("   ⚠️  Rotation should have been applied but wasn't")
                else:
                    print(f"⚠️  Invalid winding value: {expected_winding}")
        else:
            print('=' * 70)
            print('SUMMARY')
            print('=' * 70)
            print(f"⚠️  Pages have different rotations: {unique_rotations}")
            print("   This is unusual - all pages should have the same rotation")
        
        doc.close()
        
    except Exception as e:
        print(f"❌ Error analyzing PDF: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_rotation.py <pdf_path> [winding_value]")
        print()
        print("Examples:")
        print("  python check_rotation.py processed.pdf")
        print("  python check_rotation.py processed.pdf 4")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    winding = None
    
    if len(sys.argv) >= 3:
        try:
            winding = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  Invalid winding value: {sys.argv[2]}, ignoring")
    
    check_pdf_rotation(pdf_path, winding)


if __name__ == "__main__":
    main()

