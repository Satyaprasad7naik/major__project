import sqlite3
import os
from app.services.excel_sync import sync_excel_to_db, get_sync_status
from app.services.auto_insights import generate_insights

db_path = "retail_clothing.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("Wiping old data from retail_clothing.db...")
for table in ["products", "inventory", "sales_events", "suppliers", "auto_insights", "sync_logs", "auth_logs", "login_events"]:
    try:
        c.execute(f"DELETE FROM {table}")
        print(f"  Cleared {table}")
    except Exception as e:
        print(f"  Warning on {table}: {e}")

conn.commit()
conn.close()

print("\nTriggering Excel Sync from live_data/...")
result = sync_excel_to_db(db_path=db_path, live_data_dir="live_data", force=True)
print("Sync Result:", result)

conn = sqlite3.connect(db_path)
c = conn.cursor()
for table in ["products", "inventory", "sales_events", "suppliers", "auto_insights"]:
    cnt = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {cnt} rows")

print("\nSample Products:")
for row in c.execute("SELECT sku, style_name, category, unit_cost, retail_price, source FROM products LIMIT 5").fetchall():
    print(" ", row)

print("\nSample Inventory:")
for row in c.execute("SELECT sku, stock_count, reorder_point, location, source FROM inventory LIMIT 5").fetchall():
    print(" ", row)

print("\nSample Sales Events:")
for row in c.execute("SELECT event_id, sku, units_sold, sale_date, channel, source FROM sales_events LIMIT 5").fetchall():
    print(" ", row)

conn.close()
