"""Migration 001: Add InsightOS tables (auto_insights, purchase_orders, simulation_results)"""
import logging

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- 1. auto_insights
CREATE TABLE IF NOT EXISTS auto_insights (
    insight_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    payload_json TEXT,
    sku TEXT,
    supplier_id TEXT,
    status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_auto_insights_domain_status ON auto_insights(domain, status);
CREATE INDEX IF NOT EXISTS idx_auto_insights_created ON auto_insights(created_at DESC);

-- 2. purchase_orders
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL,
    supplier_id TEXT NOT NULL,
    unit_cost REAL,
    total_cost REAL,
    status TEXT DEFAULT 'DRAFT',
    recommended_by TEXT,
    insight_id TEXT REFERENCES auto_insights(insight_id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_po_sku ON purchase_orders(sku);

-- 3. simulation_results
CREATE TABLE IF NOT EXISTS simulation_results (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    domain TEXT NOT NULL,
    parameters TEXT,
    expected_alerts TEXT,
    actual_alerts TEXT,
    passed BOOLEAN,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def run_migration(conn):
    """Execute migration on a SQLite connection."""
    conn.executescript(MIGRATION_SQL)
    conn.commit()
    logger.info("Migration 001 applied: InsightOS tables created")