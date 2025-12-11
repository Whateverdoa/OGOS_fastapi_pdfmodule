import requests
import json
import os

# Configuration from user provided values (hardcoded for this script to avoid .env issues if ignored)
BASE_URL = "https://orders.optimumgroup.nl/OrderServiceTest"
TOKEN_URL = "https://orders.optimumgroup.nl/OrderServiceTest/api/token"
USERNAME = "helloprint"
PASSWORD = "7D9ACE2E-FA66-48AC-A142-7B3F68EB9F8C"

LOCATIONS = ["L02", "L03"]

ENDPOINTS = [
    "api/material/Locations",
    "api/material/Material",
    "api/material/Adhesives",
    "api/material/coresizes",
    "api/material/pouches",
    "api/material/pouchclosures",
    "api/material/producttypes",
    "api/material/shapes",
    "api/material/shiptocountries",
    "api/material/shippingmethods"
]

def get_token():
    print("Getting access token...")
    payload = {
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD
    }
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=10)
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        else:
            print(f"Failed to get token: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Exception getting token: {e}")
        return None

def fetch_data(token):
    results = {}
    # Add Key header (GUID) as discovered
    headers = {
        "Authorization": f"Bearer {token}",
        "Key": "7D9ACE2E-FA66-48AC-A142-7B3F68EB9F8C" 
    }
    
    # First fetch Locations (global)
    print(f"Fetching global Locations...")
    try:
        url = f"{BASE_URL}/api/material/Locations"
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            try:
                results["Locations"] = response.json()
            except:
                results["Locations"] = response.text
        else:
            results["Locations"] = f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        results["Locations"] = f"Exception: {str(e)}"

    # Fetch per-location endpoints
    for loc in LOCATIONS:
        results[loc] = {}
        print(f"\nFetching data for Location: {loc}")
        for endpoint in ENDPOINTS:
            if endpoint == "api/material/Locations":
                continue 
            
            name = endpoint.split('/')[-1]
            url = f"{BASE_URL}/{endpoint}?LocationCode={loc}"
            print(f"  Fetching {name}...")
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        results[loc][name] = data
                    except:
                        results[loc][name] = response.text
                else:
                    # Capture text for debugging
                    results[loc][name] = f"Error: {response.status_code} - {response.text}"
            except Exception as e:
                results[loc][name] = f"Exception: {str(e)}"
                
    return results

def generate_markdown(data):
    md = "# Material API Collection\n\n"
    md += f"Base URL: {BASE_URL}\n\n"
    
    # Locations
    md += "## Global Locations\n"
    md += "```json\n"
    md += json.dumps(data.get("Locations"), indent=2)
    md += "\n```\n\n"
    
    for loc in LOCATIONS:
        md += f"## Location: {loc}\n"
        loc_data = data.get(loc, {})
        for name, content in loc_data.items():
            md += f"### {name}\n"
            md += "```json\n"
            md += json.dumps(content, indent=2)
            md += "\n```\n\n"
            
    return md

if __name__ == "__main__":
    token = get_token()
    if token:
        data = fetch_data(token)
        md_content = generate_markdown(data)
        
        with open("material.md", "w") as f:
            f.write(md_content)
        
        print("\nDone. Saved to material.md")
    else:
        print("Aborting due to auth failure.")
