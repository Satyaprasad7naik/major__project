import sqlite3

conn = sqlite3.connect('retail_clothing.db')
c = conn.cursor()
tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
print("Tables in retail_clothing.db:")
for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  - {t}: {cnt} rows")

print("\nSample Products:")
try:
    for row in c.execute("SELECT * FROM products LIMIT 5").fetchall():
        print(" ", row)
except Exception as e:
    print("  Error:", e)

print("\nSample Inventory:")
try:
    for row in c.execute("SELECT * FROM inventory LIMIT 5").fetchall():
        print(" ", row)
except Exception as e:
    print("  Error:", e)

print("\nSample Sales Events:")
try:
    for row in c.execute("SELECT * FROM sales_events LIMIT 5").fetchall():
        print(" ", row)
except Exception as e:
    print("  Error:", e)
