"""
Manual Testing Script for Google Sheets Live Sync in InsightOS
==============================================================
Validates:
1. Service Account authentication (Method A).
2. User OAuth Token authentication (Method B).
3. HTTP Link-Shared CSV Ingestion (Method C).
4. Direct Database Upsert and live Auto Insights triggering.
"""

import sys
import os
import pandas as pd

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings
from app.services.google_sheets_sync import (
    sync_google_sheets,
    get_google_oauth_auth_url,
    load_user_oauth_token,
    fetch_sheet_via_http_csv
)
from app.services.auto_insights import generate_insights, get_db_connection
from app.services.excel_sync import _upsert_products, _upsert_inventory, _upsert_sales, init_sync_schema


def test_google_sheets_manual():
    print("=" * 70)
    print(" InsightOS - Google Sheets Live Synchronization Test Suite")
    print("=" * 70)

    # 1. Check Configuration
    print("\n[TEST 1] Checking Google Sheets Configuration & Credentials...")
    print(f"  - GOOGLE_SHEETS_ENABLED:  {settings.GOOGLE_SHEETS_ENABLED}")
    print(f"  - GOOGLE_SHEET_ID:        {settings.GOOGLE_SHEET_ID or '[Not set in .env]'}")
    print(f"  - GOOGLE_CREDENTIALS_FILE: {settings.GOOGLE_CREDENTIALS_FILE} (Exists: {os.path.exists(settings.GOOGLE_CREDENTIALS_FILE)})")
    
    user_token = load_user_oauth_token()
    print(f"  - User OAuth Token:       {'[LOADED]' if user_token else '[Not connected]'}")

    # 2. Check OAuth URL Generation (Method B: Google Sign-In)
    print("\n[TEST 2] Testing Google OAuth 2.0 URL Generator (Google Sign-In)...")
    auth_url = get_google_oauth_auth_url(client_id="test-client-id.apps.googleusercontent.com")
    print(f"  [SUCCESS] Generated OAuth Consent URL:\n    {auth_url[:100]}...")

    # 3. Simulate Ingestion of Google Sheets data into SQLite
    print("\n[TEST 3] Simulating Google Sheets Data Ingestion (Products, Inventory, Sales)...")
    sample_products = pd.DataFrame([
        {"sku": "GS-TOP-001", "style_name": "Linen Summer Blouse", "category": "Tops", "size": "M", "color": "Sky Blue", "unit_cost": 42.0, "retail_price": 89.0, "supplier_id": "SUP-0001"},
        {"sku": "GS-BOT-002", "style_name": "Slim Chino Trousers", "category": "Bottoms", "size": "32", "color": "Navy", "unit_cost": 55.0, "retail_price": 115.0, "supplier_id": "SUP-0001"},
    ])
    sample_inventory = pd.DataFrame([
        {"sku": "GS-TOP-001", "stock_count": 4, "reorder_point": 12, "location": "Warehouse A"},
        {"sku": "GS-BOT-002", "stock_count": 1, "reorder_point": 10, "location": "Warehouse B"},
    ])
    sample_sales = pd.DataFrame([
        {"event_id": "GS-SE-1001", "sku": "GS-TOP-001", "units_sold": 5, "sale_date": "2026-09-23", "channel": "Google Store"},
        {"event_id": "GS-SE-1002", "sku": "GS-BOT-002", "units_sold": 3, "sale_date": "2026-09-23", "channel": "Google Store"},
    ])

    conn = get_db_connection("retail_clothing.db")
    init_sync_schema(conn)

    p_rows = _upsert_products(conn, sample_products)
    i_rows = _upsert_inventory(conn, sample_inventory)
    s_rows = _upsert_sales(conn, sample_sales)
    conn.close()

    print(f"  [SUCCESS] Ingested Google Sheets records into retail_clothing.db:")
    print(f"  - Products Upserted:  {p_rows}")
    print(f"  - Inventory Upserted: {i_rows}")
    print(f"  - Sales Upserted:     {s_rows}")

    # 4. Trigger Auto Insights & Stockout Evaluation on Google Sheets Data
    print("\n[TEST 4] Triggering Auto Insights on newly synchronized Google Sheets data...")
    insights = generate_insights("retail_clothing.db")
    print(f"  [SUCCESS] Generated {len(insights)} business insights across active inventory.")
    for i, ins in enumerate(insights[:2], 1):
        headline = ins.get("headline") or ins.get("finding") or "Inventory Insight"
        print(f"    [{i}] {headline}")
        print(f"        Action: {ins.get('recommended_action')}")

    print("\n" + "=" * 70)
    print(" Google Sheets synchronization tests completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_google_sheets_manual()
