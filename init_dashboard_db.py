import sqlite3
import os

DATABASE_PATH = "./deriveinsights_dashboard.db"

def initialize_dashboard_db():
    print(f"Initializing Dashboard Database at {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create dashboards table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dashboards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dashboard_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        owner_id TEXT,
        widgets TEXT,
        layout TEXT,
        is_deployed BOOLEAN DEFAULT 0,
        created_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("Dashboard Database initialized successfully!")

if __name__ == "__main__":
    initialize_dashboard_db()
