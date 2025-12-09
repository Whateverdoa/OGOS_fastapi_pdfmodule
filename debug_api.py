import requests
import json

BASE_URL = "https://orders.optimumgroup.nl/OrderServiceTest"
TOKEN_URL = "https://orders.optimumgroup.nl/OrderServiceTest/api/token"

USERS = [
    {"username": "helloprint", "password": "7D9ACE2E-FA66-48AC-A142-7B3F68EB9F8C", "guid": "7D9ACE2E-FA66-48AC-A142-7B3F68EB9F8C"},
    {"username": "drukwerkdeal", "password": "267a5420-7d6e-4c03-a3f3-227cba1639a5", "guid": "267a5420-7d6e-4c03-a3f3-227cba1639a5"}
]

def get_token(username, password):
    payload = {
        "grant_type": "password",
        "username": username,
        "password": password
    }
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
    except:
        pass
    return None

def test_endpoint(name, url, token, headers=None, params=None):
    if headers is None: headers = {}
    if params is None: params = {}
    
    headers["Authorization"] = f"Bearer {token}"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        print(f"[{name}] {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print(f"[{name}] Exception: {e}")

def run_tests():
    for user in USERS:
        print(f"\n--- Testing User: {user['username']} ---")
        token = get_token(user['username'], user['password'])
        if not token:
            print("Failed to get token")
            continue
            
        guid = user['guid']
        
        # Test Locations
        print("\nTesting Locations:")
        base_loc = f"{BASE_URL}/api/material/Locations"
        
        test_endpoint("No Params", base_loc, token)
        test_endpoint("Header SupplierId", base_loc, token, headers={"SupplierId": guid})
        test_endpoint("Query SupplierId", base_loc, token, params={"SupplierId": guid})
        test_endpoint("Query supplierId", base_loc, token, params={"supplierId": guid})
        test_endpoint("Query Key", base_loc, token, params={"Key": guid})
        test_endpoint("Query key", base_loc, token, params={"key": guid})
        test_endpoint("Header Key", base_loc, token, headers={"Key": guid})
        test_endpoint("Header key", base_loc, token, headers={"key": guid})
        test_endpoint("Header Guid", base_loc, token, headers={"Guid": guid})
        
        # Test Adhesives with L02
        print("\nTesting Adhesives (L02):")
        base_adh = f"{BASE_URL}/api/material/Adhesives"
        
        test_endpoint("Query LocationCode=L02", base_adh, token, params={"LocationCode": "L02"})
        test_endpoint("Query LocationCode=GUID", base_adh, token, params={"LocationCode": guid})
        test_endpoint("Query LocationCode=L02 + Header Key", base_adh, token, headers={"Key": guid}, params={"LocationCode": "L02"})
        test_endpoint("Query LocationCode=L02 + Header SupplierId", base_adh, token, headers={"SupplierId": guid}, params={"LocationCode": "L02"})
        test_endpoint("Query LocationCode=L02 + Query SupplierId", base_adh, token, params={"LocationCode": "L02", "SupplierId": guid})
        
        # Test Adhesives with NL (just in case)
        print("\nTesting Adhesives (NL):")
        test_endpoint("Query LocationCode=NL", base_adh, token, params={"LocationCode": "NL"})

if __name__ == "__main__":
    run_tests()
