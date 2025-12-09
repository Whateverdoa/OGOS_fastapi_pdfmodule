
import fitz # PyMuPDF

def get_dims(path):
    doc = fitz.open(path)
    page = doc[0]
    
    # 1 pt = 1/72 inch; 1 inch = 25.4 mm -> 1 pt = 0.352778 mm
    pts_to_mm = 0.352778
    
    w_mm = page.rect.width * pts_to_mm
    h_mm = page.rect.height * pts_to_mm
    
    # Check rotation
    rot = page.rotation
    
    print(f"File: {path}")
    print(f"  MediaBox (mm): {w_mm:.2f} x {h_mm:.2f}")
    print(f"  Rotation: {rot}")
    
    # Effective visual dimensions
    if rot in (90, 270):
        print(f"  Effective Visual: {h_mm:.2f} x {w_mm:.2f}")
    else:
        print(f"  Effective Visual: {w_mm:.2f} x {h_mm:.2f}")
    print("-" * 30)

orig = "pdf_storage/original/20251205_115324_6001946892-1_design_1.pdf"
proc = "pdf_storage/processed/20251205_115325_6001946892-1_design_1_processed_6001946892-1.pdf"

print("--- ANALYSIS OF ID 6001946892-1 ---\n")
get_dims(orig)
get_dims(proc)
