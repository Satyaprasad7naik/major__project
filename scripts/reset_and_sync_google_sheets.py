"""
Reset Database and Ingest Pure Google Sheets Data
================================================
Wipes all old/sample retail clothing data and loads ONLY the live data from Google Sheets.
"""
import sqlite3
import os
import sys

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings
from app.services.google_sheets_sync import sync_google_sheets
from app.services.excel_sync import sync_excel_to_db
from app.services.auto_insights import generate_insights

DB_PATH = "retail_clothing.db"

def reset_and_sync():
    print("=" * 60)
    print("Resetting database to ONLY use Google Sheets data...")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    tables = ["products", "inventory", "sales_events", "suppliers", "purchase_orders", "auto_insights", "sync_logs"]
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table};")
            print(f"  [CLEARED] Truncated table: {table}")
        except Exception as e:
            print(f"  [SKIP] Table {table}: {e}")
    conn.commit()
    conn.close()
    
    print("\n[Step 1/2] Ingesting Live Data from Google Sheets...")
    sheet_id = settings.GOOGLE_SHEET_ID
    sync_res = sync_google_sheets(sheet_id=sheet_id, db_path=DB_PATH)
    print(f"  Result: {sync_res}")
    
    # If network/API backup needed, also run excel sync on google_sheets_backup.xlsx
    if sync_res.get("status") != "SUCCESS" or sync_res.get("rows_synced", 0) == 0:
        print("  Running fallback sync on google_sheets_backup.xlsx...")
        fb_res = sync_excel_to_db(db_path=DB_PATH, live_data_dir="live_data", force=True)
        print(f"  Backup Sync Result: {fb_res}")
        
    print("\n[Step 2/2] Generating Fresh Auto-Insights for Retail Products...")
    insights = generate_insights(DB_PATH)
    print(f"  Generated {len(insights)} live insights.")
    
    # Verification
    print("\n" + "=" * 60)
    print("Verification of Database Contents:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for table in ["products", "inventory", "sales_events", "suppliers", "auto_insights"]:
        try:
            cnt = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  Table '{table}': {cnt} rows")
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            rows = cursor.fetchall()
            for r in rows:
                print(f"    -> {r}")
        except Exception as e:
            print(f"  Table '{table}': error: {e}")
    conn.close()
    print("=" * 60)

if __name__ == "__main__":
    reset_and_sync()
