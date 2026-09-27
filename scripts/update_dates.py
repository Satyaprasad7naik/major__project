import sqlite3
from datetime import datetime

conn = sqlite3.connect('retail_insight.db')
cur = conn.cursor()

# Get max alert date
max_date_str = cur.execute('SELECT MAX(created_at) FROM alerts').fetchone()[0]
max_dt = datetime.strptime(max_date_str, '%Y-%m-%d %H:%M:%S')
now_dt = datetime.now()
delta_days = (now_dt - max_dt).days

print(f"Adjusting database dates by +{delta_days} days to align with current time ({now_dt.date()})...")

tables_date_cols = [
    ('alerts', 'created_at'),
    ('login_events', 'created_at'),
    ('transactions', 'created_at'),
    ('sales_events', 'sale_date')
]

for table, col in tables_date_cols:
    try:
        cur.execute(f"UPDATE {table} SET {col} = datetime({col}, '+{delta_days} days') WHERE {col} IS NOT NULL")
        print(f"Updated {table}.{col}")
    except Exception as e:
        print(f"Error updating {table}: {e}")

conn.commit()
conn.close()
print("Timestamp normalization complete!")
