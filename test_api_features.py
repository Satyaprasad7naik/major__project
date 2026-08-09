import requests
import json
import time

def test_query(query, domain="general"):
    # Try 127.0.0.1 explicitly
    url = "http://127.0.0.1:8080/api/v1/query"
    payload = {
        "query": query,
        "domain": domain
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing Query: '{query}'")
    print(f"URL: {url}")
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=600)
        duration = time.time() - start_time
        print(f"Time taken: {duration:.2f}s")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("SQL Generated:", result.get("sql"))
            print("Status:", result.get("status"))
        else:
            print("Error Response:", response.text)
    except Exception as e:
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception Message: {str(e)}")

if __name__ == "__main__":
    test_query("How many users are there?")
