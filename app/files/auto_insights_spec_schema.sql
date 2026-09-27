-- Auto Insights Spec Table (per AUTO_INSIGHTS_FEATURE.md specification)
-- New table with confidence scoring and spec-compliant columns

CREATE TABLE IF NOT EXISTS auto_insights_spec (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id TEXT NOT NULL UNIQUE,           -- INS-20260829-001
    domain TEXT NOT NULL DEFAULT 'retail_clothing',
    insight_type TEXT NOT NULL,                -- stockout_risk, sales_drop, inventory_aging, demand_spike, critical_stockout, supplier_risk
    severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,      -- 0.0-1.0 per spec Section 3.3
    confidence_explanation TEXT,               -- human-readable breakdown
    rule_version TEXT NOT NULL DEFAULT '1.0',  -- spec version
    product_id TEXT,
    product_name TEXT,
    sku TEXT,
    supplier_id TEXT,
    payload_json TEXT NOT NULL,                -- full context for drill-down
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ACKNOWLEDGED','RESOLVED','DISMISSED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT,
    resolved_at TIMESTAMP,
    is_read INTEGER NOT NULL DEFAULT 0
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_domain_date ON auto_insights_spec(domain, date(created_at));
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_status ON auto_insights_spec(status);
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_type ON auto_insights_spec(insight_type);
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_unread ON auto_insights_spec(is_read, domain) WHERE is_read = 0;
CREATE INDEX IF NOT EXISTS idx_auto_insights_spec_insight_id ON auto_insights_spec(insight_id);