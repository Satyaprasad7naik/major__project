import glob
import sqlite3

db_files = glob.glob("*.db")
print("Database files:", db_files)
for db in db_files:
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\nDB: {db}")
    for t in tables:
        try:
            cnt = cursor.execute(f"SELECT count(*) FROM [{t}]").fetchone()[0]
            print(f"  {t}: {cnt} rows")
        except Exception as e:
            print(f"  {t}: err {e}")
    conn.close()
