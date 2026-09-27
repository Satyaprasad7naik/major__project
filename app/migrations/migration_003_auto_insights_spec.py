"""Migration 003: Add auto_insights_spec table (per AUTO_INSIGHTS_FEATURE.md spec)"""
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- auto_insights_spec table (spec-compliant)
CREATE TABLE IF NOT EXISTS auto_insights_spec (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL DEFAULT 'retail_clothing',
    insight_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    confidence_explanation TEXT,
    rule_version TEXT NOT NULL DEFAULT '1.0',
    product_id TEXT,
    product_name TEXT,
    sku TEXT,
    supplier_id TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ACKNOWLEDGED','RESOLVED','DISMISSED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT,
    resolved_at TIMESTAMP,
    is_read INTEGER NOT NULL DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_domain_date ON auto_insights_spec(domain, date(created_at));
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_status ON auto_insights_spec(status);
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_type ON auto_insights_spec(insight_type);
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_unread ON auto_insights_spec(is_read, domain) WHERE is_read = 0;
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_insight_id ON auto_insights_spec(insight_id);
"""

# Legacy to spec insight_type mapping
LEGACY_TO_SPEC_TYPE = {
    'stockout_risk': 'stockout_risk',
    'critical_stockout': 'critical_stockout',
    'sales_drop': 'sales_drop',
    'supplier_risk': 'supplier_risk',
}

LEGACY_TO_SPEC_SEVERITY = {
    'CRITICAL': 'CRITICAL',
    'HIGH': 'HIGH',
    'MEDIUM': 'MEDIUM',
    'LOW': 'LOW',
}

def run_migration(conn):
    """Execute migration on a SQLite connection."""
    conn.executescript(MIGRATION_SQL)
    conn.commit()
    logger.info("Migration 003 applied: auto_insights_spec table created")

    # Backfill from legacy auto_insights table if it exists
    backfill_legacy_insights(conn)


def backfill_legacy_insights(conn):
    """Migrate data from legacy auto_insights to auto_insights_spec."""
    cursor = conn.cursor()

    # Check if legacy table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_insights'")
    if not cursor.fetchone():
        logger.info("Legacy auto_insights table does not exist, skipping backfill")
        return

    # Get legacy columns
    cursor.execute("PRAGMA table_info(auto_insights)")
    legacy_cols = {row[1] for row in cursor.fetchall()}

    if 'insight_id' not in legacy_cols:
        logger.warning("Legacy auto_insights missing insight_id column, skipping backfill")
        return

    # Fetch legacy insights
    cursor.execute("""
        SELECT
            insight_id, domain, insight_type, severity, title, description,
            payload_json, sku, supplier_id, status, created_at,
            acknowledged_at, acknowledged_by
        FROM auto_insights
        WHERE status != 'DISMISSED'
    """)
    legacy_insights = cursor.fetchall()

    if not legacy_insights:
        logger.info("No legacy insights to backfill")
        return

    logger.info(f"Backfilling {len(legacy_insights)} legacy insights to auto_insights_spec")

    inserted = 0
    for legacy in legacy_insights:
        insight_id = legacy['insight_id']
        domain = legacy['domain'] or 'retail_clothing'
        insight_type = LEGACY_TO_SPEC_TYPE.get(legacy['insight_type'], legacy['insight_type'])
        severity = LEGACY_TO_SPEC_SEVERITY.get(legacy['severity'], 'MEDIUM')
        title = legacy['title']
        description = legacy['description']
        payload_json = legacy['payload_json'] or '{}'
        sku = legacy['sku']
        supplier_id = legacy['supplier_id']
        status = legacy['status'] or 'ACTIVE'
        created_at = legacy['created_at']
        acknowledged_at = legacy['acknowledged_at']
        acknowledged_by = legacy['acknowledged_by']

        # Extract product_id and product_name from payload_json if available
        product_id = None
        product_name = None
        try:
            import json
            payload = json.loads(payload_json)
            product_id = payload.get('product_id') or payload.get('sku')
            product_name = payload.get('product_name') or payload.get('style_name')
        except Exception:
            pass

        # Calculate basic confidence (0.7 for migrated data)
        confidence = 0.7
        confidence_explanation = "Migrated from legacy auto_insights table"
        rule_version = "1.0"
        is_read = 1 if status == 'ACKNOWLEDGED' else 0
        resolved_at = acknowledged_at if status in ('ACKNOWLEDGED', 'RESOLVED') else None

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO auto_insights_spec
                (insight_id, domain, insight_type, severity, title, description,
                 confidence, confidence_explanation, rule_version,
                 product_id, product_name, sku, supplier_id,
                 payload_json, status, created_at, acknowledged_at,
                 acknowledged_by, resolved_at, is_read)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                insight_id, domain, insight_type, severity, title, description,
                confidence, confidence_explanation, rule_version,
                product_id, product_name, sku, supplier_id,
                payload_json, status, created_at, acknowledged_at,
                acknowledged_by, resolved_at, is_read
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            logger.warning(f"Failed to backfill insight {insight_id}: {e}")

    conn.commit()
    logger.info(f"Backfill complete: {inserted} insights migrated to auto_insights_spec")


def run_migration_on_all_databases():
    """Run migration on all known database files."""
    project_root = Path(__file__).parent.parent.parent
    db_files = [
        project_root / "retail_clothing.db",
        project_root / "derivinsightnew.db",
        project_root / "derivinsight_alerts.db",
    ]

    for db_path in db_files:
        if db_path.exists():
            logger.info(f"Running migration on {db_path}")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                run_migration(conn)
            finally:
                conn.close()
        else:
            logger.info(f"Database not found, skipping: {db_path}")


if __name__ == "__main__":
    run_migration_on_all_databases()