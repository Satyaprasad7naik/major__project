"""
Migration 002: Auto Insights table enhancement and migration across SQLite databases.
Ensures auto_insights table exists with all required columns for InsightOS.
"""

import sqlite3
import os
import glob
from app.core.logger import logger


def run_migration_for_db(db_path: str):
    """Ensure auto_insights table has all required columns in a specific database."""
    if not os.path.exists(db_path):
        logger.info(f"[Migration 002] DB file does not exist, skipping: {db_path}")
        return

    logger.info(f"[Migration 002] Running auto_insights migration on {db_path}...")
    conn = sqlite3.connect(db_path)
    try:
        # Create table if not exists with unified schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_id TEXT,
                domain TEXT DEFAULT 'retail_clothing',
                insight_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                product_id INTEGER,
                product_name TEXT,
                sku TEXT,
                supplier_id TEXT,
                payload_json TEXT,
                status TEXT DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0,
                acknowledged_at TIMESTAMP,
                acknowledged_by TEXT
            );
        """)
        conn.commit()

        # Check existing columns to add missing ones if table existed previously
        cursor = conn.execute("PRAGMA table_info(auto_insights)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        col_definitions = [
            ("insight_id", "TEXT"),
            ("domain", "TEXT DEFAULT 'retail_clothing'"),
            ("product_id", "INTEGER"),
            ("product_name", "TEXT"),
            ("sku", "TEXT"),
            ("supplier_id", "TEXT"),
            ("payload_json", "TEXT"),
            ("status", "TEXT DEFAULT 'ACTIVE'"),
            ("is_read", "INTEGER DEFAULT 0"),
            ("acknowledged_at", "TIMESTAMP"),
            ("acknowledged_by", "TEXT"),
        ]

        for col_name, col_type in col_definitions:
            if col_name not in existing_cols:
                logger.info(f"[Migration 002] Adding column {col_name} to auto_insights in {db_path}")
                try:
                    conn.execute(f"ALTER TABLE auto_insights ADD COLUMN {col_name} {col_type};")
                except Exception as ex:
                    logger.warning(f"[Migration 002] Could not add column {col_name}: {ex}")

        conn.commit()
        logger.info(f"[Migration 002] Successfully completed migration on {db_path}")
    except Exception as e:
        logger.error(f"[Migration 002] Error migrating {db_path}: {e}")
        conn.rollback()
    finally:
        conn.close()


def run_all_migrations():
    """Run migration across all .db files in project directory."""
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_files = glob.glob(os.path.join(project_dir, "*.db"))

    # Also target primary database names explicitly
    target_dbs = [
        "retail_clothing.db",
        "retail_insight.db",
        "derivinsightnew.db",
        "deriveinsights_dashboard.db",
    ]

    for db_name in target_dbs:
        full_path = os.path.join(project_dir, db_name)
        if full_path not in db_files:
            db_files.append(full_path)

    for db_path in db_files:
        run_migration_for_db(db_path)


if __name__ == "__main__":
    run_all_migrations()
