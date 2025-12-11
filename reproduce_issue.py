
import json
from app.api.endpoints.pdf import _detect_reseller

def test_reseller_detection():
    # Scenario: File accidentally renamed to " .PDF"
    filename = " .PDF"
    
    # Generic config without obvious reseller keys
    config_dict = {
        "ReferenceAtCustomer": "5623221-8841620",
        "Width": 48.0,
        "Height": 70.0,
        "Winding": 8
    }
    
    # Context text (simulating "filename json_filename")
    context_text = f"{filename} some_config.json"
    
    is_reseller = _detect_reseller(context_text, config_dict)
    
    print(f"Filename: '{filename}'")
    print(f"Config: {config_dict}")
    print(f"Detected as Reseller? {is_reseller}")
    
    if not is_reseller:
        print("\n[FAILURE CONFIRMED] System failed to identify this as a reseller order.")
        print("This prevents automatic rotation mapping and dimension swapping.")
    else:
        print("\n[UNEXPECTED] System somehow detected this as reseller.")

if __name__ == "__main__":
    test_reseller_detection()
