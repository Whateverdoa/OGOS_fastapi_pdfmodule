#!/usr/bin/env python3
"""Test the fix for job 5633093-8858525 and show new output"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

from app.core.pdf_processor import PDFProcessor
from app.core.pdf_analyzer import PDFAnalyzer
from app.models.schemas import PDFJobConfig, ShapeType

def main():
    # Load order data from JSON
    json_path = "/Volumes/172.27.23.70/OGOS_DWD_PDC/output/failed/5633093-8858525.json"
    original_pdf = "pdf_storage/original/20251208_090528_5633093_8858525.PDF"
    
    print("=" * 80)
    print("TESTING FIX FOR JOB 5633093-8858525")
    print("=" * 80)
    
    # Read JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Extract from Lines array (first line)
    line = config.get('Lines', [{}])[0] if config.get('Lines') else {}
    width = line.get('Width', config.get('Width', 0))
    height = line.get('Height', config.get('Height', 0))
    shape = (line.get('Shape') or config.get('Shape', '')).lower()
    winding = line.get('Winding') or config.get('Winding')
    reference = config.get('Reference_at_customer', config.get('ReferenceAtCustomer', config.get('reference', '5633093-8858525')))
    
    print(f"\n📋 Order Input:")
    print(f"  Width: {width}mm")
    print(f"  Height: {height}mm")
    print(f"  Shape: {shape}")
    print(f"  Winding: {winding}")
    
    # Create job config (simulating what the API would do)
    # Winding 3 → 90° rotation → swap dimensions for reseller
    from app.utils.winding_router import route_by_winding
    rotation = route_by_winding(winding) if winding else 0
    
        # Simulate reseller logic: swap dimensions for 90°/270°
    original_width = width
    original_height = height
    if rotation in (90, 270):
        width, height = height, width
        print(f"\n🔄 Reseller logic: Winding {winding} → {rotation}° rotation")
        print(f"   Swapped dimensions: {original_height}mm x {original_width}mm → {width}mm x {height}mm")
    
    job_config = PDFJobConfig(
        reference=reference,
        description=config.get('Description', ''),
        shape=ShapeType.rectangle if shape == 'rectangle' else ShapeType.circle,
        width=float(width),
        height=float(height),
        radius=float(config.get('Radius', 0)),
        spot_color_name="stans",
        line_thickness=0.5,
        winding=2  # Normalized to 2 for resellers
    )
    
    print(f"\n⚙️  Final Job Config:")
    print(f"  Dimensions: {job_config.width}mm x {job_config.height}mm")
    print(f"  Shape: {job_config.shape}")
    
    # Process PDF
    print(f"\n🔄 Processing PDF...")
    processor = PDFProcessor()
    result = processor.process_pdf(original_pdf, job_config)
    
    if result['success']:
        output_path = result['output_path']
        print(f"✓ Processing successful")
        print(f"  Output: {output_path}")
        
        # Analyze the output
        print(f"\n📊 Analyzing output PDF...")
        analyzer = PDFAnalyzer()
        analysis = analyzer.analyze_pdf(output_path)
        
        stans_dielines = [d for d in analysis.get('detected_dielines', []) 
                          if d.get('dieline_type') == 'stans_dieline']
        
        actual_w = None
        actual_h = None
        
        if stans_dielines:
            actual_w = stans_dielines[0].get('path_width', 0)
            actual_h = stans_dielines[0].get('path_height', 0)
            
            print(f"\n✂️  Stans Dimensions in Output PDF:")
            print(f"  Actual: {actual_w:.2f}mm x {actual_h:.2f}mm")
            print(f"  Expected: {job_config.width:.2f}mm x {job_config.height:.2f}mm")
            
            width_diff = abs(actual_w - job_config.width)
            height_diff = abs(actual_h - job_config.height)
            
            if width_diff < 0.1 and height_diff < 0.1:
                print(f"\n✅ SUCCESS: Stans matches expected dimensions!")
            else:
                print(f"\n⚠️  WARNING: Stans differs from expected:")
                print(f"   Width difference: {width_diff:.2f}mm")
                print(f"   Height difference: {height_diff:.2f}mm")
        else:
            print(f"\n⚠️  No stans dieline found in output PDF")
        
        # Compare with old output
        old_output = "pdf_storage/processed/20251208_090529_5633093_8858525_processed_5633093-8858525.pdf"
        if os.path.exists(old_output) and actual_w is not None:
            print(f"\n📊 Comparing with OLD output...")
            old_analysis = analyzer.analyze_pdf(old_output)
            old_stans = [d for d in old_analysis.get('detected_dielines', []) 
                        if d.get('dieline_type') == 'stans_dieline']
            if old_stans:
                old_w = old_stans[0].get('path_width', 0)
                old_h = old_stans[0].get('path_height', 0)
                print(f"  OLD stans: {old_w:.2f}mm x {old_h:.2f}mm")
                print(f"  NEW stans: {actual_w:.2f}mm x {actual_h:.2f}mm")
                print(f"  Improvement: {((actual_w/old_w - 1) * 100):+.1f}% width, {((actual_h/old_h - 1) * 100):+.1f}% height")
        
        print(f"\n💾 Output file saved to: {output_path}")
        print(f"   You can open it to verify the stans is correct size.")
        
    else:
        print(f"\n❌ Processing failed: {result.get('message', 'Unknown error')}")
        if result.get('error'):
            print(f"   Error: {result['error']}")

if __name__ == "__main__":
    main()

