
from app.utils.winding_router import route_by_winding

def simulate_order(width, height, winding):
    print(f"--- Simulation for {width}x{height}, Winding {winding} ---")
    
    # 1. Reseller Detection
    # Since 'Winding' is present, Detection = True
    is_reseller = True 
    print(f"1. Reseller Detected: {is_reseller} (due to 'Winding' key)")
    
    # 2. Rotation Mapping
    rotation = route_by_winding(winding)
    print(f"2. Mapped Rotation: {rotation} degrees")
    
    # 3. Standard Reseller Dimension Logic
    final_w, final_h = width, height
    if is_reseller and rotation in (90, 270):
        print("   -> Rotation is 90/270, performing Standard Swap.")
        final_w, final_h = height, width
    else:
        print("   -> No Standard Swap.")
        
    print(f"3. Config after Standard Logic: {final_w} x {final_h}")
    
    # 4. Scenario A: PDF comes in as 160x200 (Portrait)
    print("\n--- Scenario A: Input PDF is 160x200 (Portrait) ---")
    pdf_w, pdf_h = 160, 200
    
    # Apply Rotation
    if rotation == 270:
        pdf_w, pdf_h = pdf_h, pdf_w # Rotated 270 swaps dims
        print(f"   -> PDF Physically Rotated 270°. New PDF Dims: {pdf_w}x{pdf_h}")
        
    # Smart Swap Check
    print(f"   -> Comparing Config ({final_w}x{final_h}) vs PDF ({pdf_w}x{pdf_h})")
    if final_w == pdf_w and final_h == pdf_h:
        print("   -> Direct Match! Processing continues correctly.")
    else:
        print("   -> Mismatch! Smart Swap Logic would engage.")

    # 4. Scenario B: PDF comes in as 200x160 (Landscape/Already Rotated?)
    print("\n--- Scenario B: Input PDF is 200x160 (Landscape) ---")
    pdf_w, pdf_h = 200, 160
    
    # Apply Rotation
    if rotation == 270:
        pdf_w, pdf_h = pdf_h, pdf_w # Rotated 270 swaps dims
        print(f"   -> PDF Physically Rotated 270°. New PDF Dims: {pdf_w}x{pdf_h}")
        
    # Smart Swap Check
    print(f"   -> Comparing Config ({final_w}x{final_h}) vs PDF ({pdf_w}x{pdf_h})")
    if final_w == pdf_w and final_h == pdf_h:
        print("   -> Direct Match! Processing continues correctly.")
    elif final_w == pdf_h and final_h == pdf_w:
        print("   -> Transposed Match! Smart Swap Logic ENGAGES.")
        final_w, final_h = final_h, final_w
        print(f"   -> Config Swapped to: {final_w}x{final_h}. Match achieved.")
    else:
        print("   -> Total Mismatch.")

simulate_order(160, 200, 4)
