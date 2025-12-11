
from app.utils.winding_router import route_by_winding

def simulate(width, height, winding):
    angle = route_by_winding(winding)
    print(f"Config: Width={width}, Height={height}, Winding={winding}")
    print(f"Calculated Rotation Angle: {angle} degrees")
    
    should_swap = angle in (90, 270)
    print(f"Should Swap Dimensions in Config? {should_swap}")
    
    if should_swap:
        print(f"Final Config: Width={height}, Height={width}")
    else:
        print(f"Final Config: Width={width}, Height={height}")
        
    artwork_w, artwork_h = 70, 48
    print(f"Artwork: {artwork_w}x{artwork_h}")
    
    if artwork_w != width or artwork_h != height:
         print("MISMATCH: The final config dimensions do not match the artwork.")
    else:
         print("MATCH: Dimensions align.")

simulate(48, 70, 2)
