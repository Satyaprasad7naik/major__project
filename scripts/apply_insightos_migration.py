#!/usr/bin/env python
"""Apply InsightOS migration to all project databases."""
import sqlite3
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.migrations import run_migration

DATABASES = [
    "retail_clothing.db",
    "derivinsightnew.db",
    "retail_insight.db",
    "deriveinsights_dashboard.db",
]

def main():
    print("Applying InsightOS migration to all databases...")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for db_name in DATABASES:
        db_path = os.path.join(project_root, db_name)
        if not os.path.exists(db_path):
            print(f"  SKIP: {db_name} not found")
            continue
        print(f"  Applying to {db_name}...")
        conn = sqlite3.connect(db_path)
        try:
            run_migration(conn)
            print(f"  OK: {db_name}")
        except Exception as e:
            print(f"  ERROR: {db_name} - {e}")
        finally:
            conn.close()
    print("Done.")

if __name__ == "__main__":
    main()