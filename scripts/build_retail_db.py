"""
Build retail_clothing.db from the 4 seed CSVs.
Run from project root: .venv\Scripts\python.exe build_retail_db.py
"""
import sqlite3
import csv
import os

DB_PATH = "retail_clothing.db"
SEED_DIR = "app/files/seed_data"
SCHEMA_OUT = "app/files/retail_clothing_schema.sql"

print("=" * 60)
print("Building retail_clothing.db from seed CSVs...")
print("=" * 60)

# Remove stale empty file
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ── Create tables matching the exact CSV column order ────────────
cur.executescript("""
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id      TEXT PRIMARY KEY,
    supplier_name    TEXT NOT NULL,
    lead_time_days   INTEGER NOT NULL,
    on_time_rate     REAL NOT NULL,
    country          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    sku              TEXT PRIMARY KEY,
    style_name       TEXT NOT NULL,
    category         TEXT NOT NULL,
    size             TEXT NOT NULL,
    color            TEXT NOT NULL,
    unit_cost        REAL NOT NULL,
    retail_price     REAL NOT NULL,
    supplier_id      TEXT NOT NULL REFERENCES suppliers(supplier_id),
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    sku              TEXT PRIMARY KEY REFERENCES products(sku),
    location         TEXT NOT NULL,
    stock_count      INTEGER NOT NULL DEFAULT 0,
    reorder_point    INTEGER NOT NULL DEFAULT 5,
    last_restocked_at TEXT
);

CREATE TABLE IF NOT EXISTS sales_events (
    event_id         TEXT PRIMARY KEY,
    sku              TEXT NOT NULL REFERENCES products(sku),
    units_sold       INTEGER NOT NULL,
    sale_date        TEXT NOT NULL,
    channel          TEXT NOT NULL
);
""")

# ── Load CSVs ────────────────────────────────────────────────────
tables_order = [
    ("suppliers",    os.path.join(SEED_DIR, "suppliers.csv")),
    ("products",     os.path.join(SEED_DIR, "products.csv")),
    ("inventory",    os.path.join(SEED_DIR, "inventory.csv")),
    ("sales_events", os.path.join(SEED_DIR, "sales_events.csv")),
]

for table, filepath in tables_order:
    if not os.path.exists(filepath):
        print(f"  MISSING: {filepath}")
        continue
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [tuple(row.values()) for row in reader if any(row.values())]
    if not rows:
        print(f"  EMPTY: {filepath}")
        continue
    placeholders = ", ".join(["?" for _ in rows[0]])
    cur.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", rows)
    conn.commit()
    verify_count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  OK {table}: loaded {len(rows)} rows -> DB has {verify_count} rows")

# ── Verification ─────────────────────────────────────────────────
print()
print("Verification:")
for table in ["suppliers", "products", "inventory", "sales_events"]:
    count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    print(f"  {table}: {count} rows | cols: {cols}")

conn.close()

# ── Regenerate retail_clothing_schema.sql ────────────────────────
print()
print(f"Regenerating {SCHEMA_OUT}...")
conn2 = sqlite3.connect(DB_PATH)
schema_lines = [
    "-- Retail Clothing Domain Schema",
    "-- Auto-generated from retail_clothing.db",
    "-- Tables: suppliers, products, inventory, sales_events",
    "",
]
for row in conn2.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC, name"):
    schema_lines.append(row[0] + ";")
    schema_lines.append("")
conn2.close()

with open(SCHEMA_OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(schema_lines))

print(f"  OK Schema written to {SCHEMA_OUT}")
print()
print("=" * 60)
print("DONE! retail_clothing.db is ready.")
print(f"DB size: {os.path.getsize(DB_PATH):,} bytes")
print("=" * 60)
