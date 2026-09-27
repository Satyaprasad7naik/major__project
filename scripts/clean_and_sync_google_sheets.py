"""
Clean all non-Google Sheet data and re-sync live Google Sheets data.
"""
import os
import sys
import sqlite3

# Ensure workspace root in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.google_sheets_sync import sync_google_sheets

def run_clean_and_sync():
    # 1. Clean live_data directory
    live_dir = "live_data"
    if os.path.exists(live_dir):
        for f in os.listdir(live_dir):
            if f.endswith(".xlsx") and f != "google_sheets_backup.xlsx":
                try:
                    os.remove(os.path.join(live_dir, f))
                    print(f"Removed non-Google Sheet file: {f}")
                except Exception as e:
                    print(f"Error removing {f}: {e}")

    # 2. Clean database tables
    db_path = "retail_clothing.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cursor.fetchall()]
    print("Existing tables:", tables)

    # Tables to wipe completely (non-Google Sheets)
    non_sheet_tables = [
        "users", "login_events", "transactions", "alerts", "audit_logs", "alert_rules",
        "warehouses", "fulfillment_orders", "inventory_items", "procurement_proposals",
        "simulation_results", "query_history", "dashboards"
    ]

    for tbl in non_sheet_tables:
        if tbl in tables:
            cursor.execute(f"DELETE FROM {tbl}")
            print(f"Cleared table: {tbl}")

    for tbl in ["products", "inventory", "sales_events", "suppliers", "auto_insights", "purchase_orders"]:
        if tbl in tables:
            cursor.execute(f"DELETE FROM {tbl}")
            print(f"Reset table: {tbl}")

    conn.commit()
    conn.close()

    # 3. Trigger pure Google Sheets sync
    print("\nSyncing from Google Sheet...")
    sync_res = sync_google_sheets()
    print("Sync result:", sync_res)

    # 4. Verify row counts
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    print("\n--- Final Database Table Counts ---")
    for tbl in tables:
        try:
            cnt = cursor.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            if cnt > 0:
                print(f"  [LIVE GOOGLE SHEETS] {tbl}: {cnt} rows")
            else:
                print(f"  [EMPTY/DELETED] {tbl}: 0 rows")
        except Exception as e:
            print(f"  {tbl}: error {e}")
    conn.close()

if __name__ == "__main__":
    run_clean_and_sync()
