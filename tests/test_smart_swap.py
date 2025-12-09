import os
import fitz
import json
import shutil
from app.core.pdf_processor import PDFProcessor
from app.models.schemas import PDFJobConfig

# Setup test paths
TEST_PDF = "/tmp/test_smart_swap.pdf"
OUTPUT_PDF = "/tmp/test_smart_swap_output.pdf"

def create_test_pdf():
    """Create a 100x50 mm PDF (Landscape)"""
    doc = fitz.open()
    # 100mm = 283.465 pt, 50mm = 141.732 pt
    page = doc.new_page(width=283.465, height=141.732)
    page.insert_text((10, 20), "Landscape 100x50", fontsize=12)
    doc.save(TEST_PDF)
    doc.close()
    print(f"Created test PDF: {TEST_PDF} (100x50mm)")

def run_test():
    create_test_pdf()

    print("=== TEST 1: Rotation Mismatch (Smart Swap) ===")
    config_dict = {
        "reference": "TEST-SWAP-001",
        "width": 50.0,   # Expecting Portrait
        "height": 100.0, # Expecting Portrait
        "shape": "rectangle",
        "spot_color_name": "stans",
        "winding": 1
    }
    
    config = PDFJobConfig(**config_dict)
    print(f"Job Config: Width={config.width}, Height={config.height} (Portrait)")
    
    processor = PDFProcessor()
    
    try:
        result = processor.process_pdf(TEST_PDF, config)
        if result['success']:
            print("✅ Processing Successful!")
            print(f"Final Config dims: {config.width}x{config.height}")
            if config.width == 100.0 and config.height == 50.0:
                 print("✅ SMART SWAP ACTIVATED: Config updated to 100x50")
            else:
                 print("❌ SMART SWAP FAILED: Config remained 50x100")
        else:
            print(f"❌ Processing Failed: {result['message']}")
    except Exception as e:
        print(f"❌ Exception: {e}")

    print("\n=== TEST 2: Normal Valid Job (No Swap) ===")
    config_dict_2 = {
        "reference": "TEST-NORMAL-001",
        "width": 100.0,  # Matches PDF
        "height": 50.0,  # Matches PDF
        "shape": "rectangle",
        "spot_color_name": "stans",
        "winding": 1
    }
    
    config2 = PDFJobConfig(**config_dict_2)
    print(f"Job Config: Width={config2.width}, Height={config2.height} (Landscape)")
    
    try:
        result = processor.process_pdf(TEST_PDF, config2)
        if result['success']:
            print("✅ Processing Successful!")
            print(f"Final Config dims: {config2.width}x{config2.height}")
            if config2.width == 100.0 and config2.height == 50.0:
                 print("✅ NO SWAP needed (Correct)")
            else:
                 print("❌ UNEXPECTED CHANGE")
        else:
            print(f"❌ Processing Failed: {result['message']}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    run_test()
