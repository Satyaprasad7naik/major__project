import requests
import time

queries = [
    ('hi', 'banking_finance'),
    ('Which products are at risk of stockout this week?', 'retail_clothing'),
    ('What is the total transaction amount by currency in the last 30 days?', 'banking_finance'),
    ('Show me all high severity incidents', 'insurance')
]

print("Running Speed Benchmark Test...\n")

for q, domain in queries:
    start = time.time()
    res = requests.post('http://127.0.0.1:8080/api/v1/query', json={'query': q, 'domain': domain})
    elapsed = time.time() - start
    data = res.json()
    print(f"=== Query: '{q}' ({domain}) ===")
    print(f"Response Time: {elapsed:.2f}s")
    print(f"Status: {data.get('status')}")
    if data.get('sql'):
        print(f"SQL: {data.get('sql').strip()}")
    if data.get('results') is not None:
        print(f"Results Count: {len(data.get('results'))}")
    if data.get('clarification_question'):
        print(f"Clarification Snippet: {data.get('clarification_question')[:80]}...")
    print("-" * 50)
