import requests
import json

def test_dashboards():
    url = "http://127.0.0.1:8080/api/v1/dashboards"
    
    # Test Create
    print("Testing Create Dashboard...")
    payload = {
        "dashboardName": "Test Security Dashboard",
        "domainType": "security",
        "userId": "user-001"
    }
    try:
        resp = requests.post(url, json=payload)
        print(f"Create Status: {resp.status_code}")
        print(f"Create Response: {resp.text}")
        
        # Test List
        print("\nTesting List Dashboards...")
        resp = requests.get(url)
        print(f"List Status: {resp.status_code}")
        print(f"List Response: {resp.text}")
    except Exception as e:
        print(f"Exception: {str(e)}")

if __name__ == "__main__":
    test_dashboards()
