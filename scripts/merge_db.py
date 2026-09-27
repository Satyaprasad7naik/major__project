import sqlite3

def merge_databases():
    src = sqlite3.connect('derivinsightnew.db')
    dst = sqlite3.connect('retail_insight.db')

    tables = ['users', 'transactions', 'login_events', 'alert_rules', 'alerts', 'audit_logs', 'dashboards']

    for table in tables:
        # Get table schema
        cur = src.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
        res = cur.fetchone()
        if not res or not res[0]:
            continue
        
        sql_schema = res[0]
        dst.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        dst.cursor().execute(sql_schema)

        # Get rows
        rows = cur.execute(f"SELECT * FROM {table}").fetchall()
        if rows:
            placeholders = ", ".join(["?"] * len(rows[0]))
            dst.cursor().executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        
        print(f"Migrated {table}: {len(rows)} rows")

    dst.commit()
    dst.close()
    src.close()
    print("Database merge completed successfully!")

if __name__ == "__main__":
    merge_databases()
