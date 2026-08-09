import requests
import json
import time

def test_sentinel():
    base_url = "http://127.0.0.1:8080/api/v1/sentinel"
    start_url = f"{base_url}/scan"
    
    print("Triggering Sentinel Scan (non-streaming)...")
    try:
        resp = requests.get(start_url, timeout=600) # Long timeout for LLM
        if resp.status_code == 200:
            result = resp.json()
            print("Scan Status:", result.get("status"))
            detections = result.get("detections", [])
            print(f"Detections Found: {len(detections)}")
            if detections:
                print("First Detection Domain:", detections[0].get("domain"))
            
            # Check history
            print("Checking scan history...")
            hist_resp = requests.get(f"{base_url}/history")
            if hist_resp.status_code == 200:
                scans = hist_resp.json().get("scans", [])
                print(f"Total Scans in History: {len(scans)}")
            else:
                print("Error fetching history")
        else:
            print(f"Error starting scan: {resp.text}")
    except Exception as e:
        print(f"Exception: {str(e)}")

if __name__ == "__main__":
    test_sentinel()
