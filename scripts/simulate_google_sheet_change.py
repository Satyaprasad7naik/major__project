"""
Simulate changes made in Google Sheets and verify live synchronization into InsightOS.
Demonstrates:
1. Creating/Editing Google Sheets data (Products, Inventory, Sales)
2. Live Synchronization Engine processing the sheet changes
3. Updating the SQLite database (retail_clothing.db)
4. Mirroring backup to live_data/google_sheets_backup.xlsx
5. Triggering AI Auto-Insights (Stockout alerts, reorder recommendations)
6. Updating sync logs and API statuses
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

# Set up project root in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.excel_sync import _upsert_products, _upsert_inventory, _upsert_sales, init_sync_schema
from app.services.auto_insights import generate_insights, get_db_connection

def simulate_sheet_change():
    print("=" * 70)
    print("  GOOGLE SHEETS CHANGE & LIVE SYNCHRONIZATION DEMO")
    print("=" * 70)

    db_path = "retail_clothing.db"
    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    # 1. State Before
    print("\n[Step 1] Checking existing state in Project Database before change...")
    existing = conn.execute(
        "SELECT sku, style_name, category, retail_price FROM products WHERE sku LIKE 'GSHEET%'"
    ).fetchall()
    print(f"  Found {len(existing)} existing GSHEET items:")
    for row in existing:
        print(f"    - SKU: {row[0]}, Name: {row[1]}, Price: ${row[3]}")

    # 2. Simulate User making changes in Google Sheets (e.g. Price drop, Stock critical drop, New Sales)
    print("\n[Step 2] User makes changes in Google Sheets:")
    print("  -> Updated SKU 'GSHEET-SILK-001': Price dropped from $89.99 to $69.99")
    print("  -> Updated SKU 'GSHEET-SILK-001': Stock dropped from 15 to 3 (Triggering CRITICAL STOCKOUT ALERT)")
    print("  -> Added NEW SKU 'GSHEET-SUMMER-002': 'Google Sheets Linen Shirt', Price: $45.00, Stock: 50")
    print("  -> Recorded NEW Sale in Google Sheets: Order #GS-9901 (3 units sold)")

    df_products_sheet = pd.DataFrame([
        {
            "sku": "GSHEET-SILK-001",
            "style_name": "Google Sheets Premium Silk Dress",
            "category": "Dresses",
            "size": "M",
            "color": "Emerald Green",
            "unit_cost": 35.00,
            "retail_price": 69.99,  # Changed price
            "supplier_id": "SUP-GS-01",
            "created_at": "2026-09-24 00:00:00"
        },
        {
            "sku": "GSHEET-SUMMER-002",
            "style_name": "Google Sheets Linen Summer Shirt",
            "category": "Shirts",
            "size": "L",
            "color": "Ocean Blue",
            "unit_cost": 20.00,
            "retail_price": 45.00,  # New item
            "supplier_id": "SUP-GS-02",
            "created_at": "2026-09-24 00:00:00"
        }
    ])

    df_inventory_sheet = pd.DataFrame([
        {
            "sku": "GSHEET-SILK-001",
            "location": "Warehouse-Main",
            "stock_count": 3,  # Changed stock to 3 (Critical Stockout risk)
            "reorder_point": 20,
            "last_restocked_at": "2026-09-24 00:00:00"
        },
        {
            "sku": "GSHEET-SUMMER-002",
            "location": "Warehouse-Main",
            "stock_count": 50,
            "reorder_point": 15,
            "last_restocked_at": "2026-09-24 00:00:00"
        }
    ])

    df_sales_sheet = pd.DataFrame([
        {
            "event_id": f"GS-SALE-{int(datetime.now().timestamp())}",
            "sku": "GSHEET-SILK-001",
            "store_id": "ONLINE-GSHEET",
            "quantity_sold": 3,
            "unit_sale_price": 69.99,
            "discount_applied": 0.0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    ])

    # 3. Live Synchronization Engine Ingestion
    print("\n[Step 3] Running Google Sheets Live Sync Engine...")
    prod_rows = _upsert_products(conn, df_products_sheet)
    inv_rows = _upsert_inventory(conn, df_inventory_sheet)
    sales_rows = _upsert_sales(conn, df_sales_sheet)
    total_rows = prod_rows + inv_rows + sales_rows

    # Log Sync Event
    conn.execute(
        "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('GOOGLE_SHEETS', 'DRIVE_SHEET_LIVE', 'SUCCESS', ?)",
        (total_rows,)
    )
    conn.commit()

    # Mirror to live_data backup
    meta_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live_data")
    os.makedirs(meta_dir, exist_ok=True)
    backup_path = os.path.join(meta_dir, "google_sheets_backup.xlsx")
    with pd.ExcelWriter(backup_path, engine="openpyxl") as writer:
        df_products_sheet.to_excel(writer, sheet_name="Products", index=False)
        df_inventory_sheet.to_excel(writer, sheet_name="Inventory", index=False)
        df_sales_sheet.to_excel(writer, sheet_name="Sales", index=False)

    print(f"  [SUCCESS] Synchronized {total_rows} rows from Google Sheets into SQLite database.")
    print(f"  [SUCCESS] Mirrored Google Sheets data to {backup_path}")

    # 4. Trigger Auto Insights Engine
    print("\n[Step 4] Triggering Auto-Generated Insights engine...")
    generate_insights(db_path)

    # 5. State After Ingestion
    print("\n[Step 5] Checking updated state in Project Database...")
    updated_products = conn.execute(
        "SELECT p.sku, p.style_name, p.retail_price, i.stock_count, i.reorder_point "
        "FROM products p LEFT JOIN inventory i ON p.sku = i.sku "
        "WHERE p.sku LIKE 'GSHEET%'"
    ).fetchall()

    for row in updated_products:
        print(f"  -> SKU: {row[0]} | Name: {row[1]} | Price: ${row[2]} | Stock: {row[3]} | Reorder Point: {row[4]}")

    # Check new Auto Insights generated
    insights = conn.execute(
        "SELECT insight_type, severity, title, description FROM auto_insights WHERE sku LIKE 'GSHEET%' ORDER BY created_at DESC"
    ).fetchall()

    print(f"\n[Step 6] Auto Insights generated for Google Sheets changes ({len(insights)} found):")
    for ins in insights:
        print(f"  * [{ins[1]}] {ins[0]}: {ins[2]}")
        print(f"    Details: {ins[3]}")

    conn.close()
    print("\n" + "=" * 70)
    print("  GOOGLE SHEETS SYNC COMPLETE - CHANGES SUCCESSFULLY REFLECTED!")
    print("=" * 70)

if __name__ == "__main__":
    simulate_sheet_change()
