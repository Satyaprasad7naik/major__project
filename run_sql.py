import sqlite3
import sys
import os

def execute_sql_file(db_path, sql_file):
    print(f"Executing {sql_file} on {db_path}...")
    if not os.path.exists(sql_file):
        print(f"Error: {sql_file} not found.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        # Split statements by semicolon, but handle cases where semicolon might be inside strings
        # For simplicity, we'll try executescript which handles multiple statements
        cursor.executescript(sql)
        conn.commit()
        conn.close()
        print(f"Successfully executed {sql_file}.")
    except Exception as e:
        print(f"Error executing {sql_file}: {e}")

if __name__ == "__main__":
    db = "derivinsightnew.db"
    execute_sql_file(db, "app/files/derivinsight_schema.sql")
    execute_sql_file(db, "derivinsight_mock_data.sql")
