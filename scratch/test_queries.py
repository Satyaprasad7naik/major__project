import asyncio
from app.orchestration.workflow import app_graph
from app.services.database import db_service

queries = [
    "Show top selling products",
    "Which products are at risk of stockout this week?",
    "Which shop had highest sales?",
    "Show profit by product",
    "What are the sales by city?",
    "Show sales by payment method",
    "Show all transactions",
    "How many units of T-Shirt were sold?",
    "What is our total revenue?",
    "Show sales by category",
    "List all suppliers",
    "Show inventory status"
]

async def test():
    print(f"Database Engine: {db_service.engine.url}")
    print("=" * 80)
    for q in queries:
        print(f"\n[QUERY]: '{q}'")
        res = await app_graph.ainvoke({
            "user_question": q,
            "domain": "retail_clothing",
            "conversation_history": [],
            "retry_count": 0
        })
        print(f"Status: {res.get('status')}")
        print(f"Generated SQL: {res.get('generated_sql')}")
        rows = res.get('query_result', [])
        print(f"Returned Rows: {len(rows) if rows else 0}")
        if rows:
            print("First row sample:", rows[0])
        insight_text = str(res.get('insight', '')).encode('ascii', errors='replace').decode('ascii')
        print("Insight:", insight_text[:120])
        print("-" * 50)

asyncio.run(test())
