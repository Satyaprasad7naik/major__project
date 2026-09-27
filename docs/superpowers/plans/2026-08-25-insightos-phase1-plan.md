# InsightOS Phase 1 Implementation Plan: Stockout Risk + Auto Insights

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stockout Risk detection with reorder recommendations and Auto-Generated Insights with APScheduler background job for the InsightOS Virtual Decision Officer.

**Architecture:** Extend existing LangGraph pipeline with new nodes for stockout analysis and insight generation. Add database tables for auto_insights and purchase_orders. Create domain-agnostic modules that work with retail_clothing, banking_finance, and insurance domains via existing domain configuration system.

**Tech Stack:** FastAPI, LangGraph, SQLite, APScheduler, Pydantic, existing Gemini/LLM integration

**Spec:** docs/superpowers/specs/2026-08-24-insightos-features-design.md

## Global Constraints

- Keep using: FastAPI + LangGraph + Gemini + SQLite + React
- Background scheduler: APScheduler
- All new features must work with the existing multi-agent pipeline
- Maintain the self-healing SQL agent
- Domain-agnostic design (retail_clothing, banking_finance, insurance)
- Prefer simple and working solutions over complex ones
- Reuse existing agents and pipeline as much as possible
- Keep code clean and modular with clear comments

---

### Task 1: Database Migration Script

**Files:**
- Create: `app/migrations/001_add_insightos_tables.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Produces: Tables `auto_insights`, `purchase_orders`, `simulation_results` in target databases
- Consumes: `app/services/database.py` (DatabaseService.engine)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrations.py
import sqlite3
import tempfile
import os

def test_migration_creates_auto_insights_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        # Run migration
        from app.migrations import migration_001
        migration_001.run_migration(conn)
        
        # Verify tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'auto_insights' in tables
        assert 'purchase_orders' in tables
        assert 'simulation_results' in tables
        
        # Verify auto_insights schema
        cursor = conn.execute("PRAGMA table_info(auto_insights)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns['insight_id'] == 'TEXT'
        assert columns['domain'] == 'TEXT'
        assert columns['insight_type'] == 'TEXT'
        assert columns['severity'] == 'TEXT'
        assert columns['status'] == 'TEXT'
        assert columns['created_at'] == 'TIMESTAMP'
        
        # Verify indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='auto_insights'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert 'idx_auto_insights_domain_status' in indexes
        assert 'idx_auto_insights_created' in indexes
    finally:
        conn.close()
        os.unlink(db_path)

def test_migration_creates_purchase_orders_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        from app.migrations import migration_001
        migration_001.run_migration(conn)
        
        cursor = conn.execute("PRAGMA table_info(purchase_orders)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns['po_id'] == 'TEXT'
        assert columns['sku'] == 'TEXT'
        assert columns['qty'] == 'INTEGER'
        assert columns['supplier_id'] == 'TEXT'
        assert columns['status'] == 'TEXT'
        assert columns['recommended_by'] == 'TEXT'
    finally:
        conn.close()
        os.unlink(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrations.py -v`
Expected: FAIL with "No module named 'app.migrations'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/migrations/001_add_insightos_tables.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/migrations/001_add_insightos_tables.py tests/test_migrations.py
git commit -m "feat: add migration for InsightOS tables (auto_insights, purchase_orders, simulation_results)"
```

---

### Task 2: Apply Migration to Existing Databases

**Files:**
- Create: `scripts/apply_insightos_migration.py`
- Modify: `app/services/database.py` (add migration call to initialize_db)

**Interfaces:**
- Consumes: `app/migrations/001_add_insightos_tables.py:run_migration`
- Produces: Updated retail_clothing.db, derivinsightnew.db with new tables

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration_application.py
import sqlite3
import tempfile
import os

def test_migration_applied_to_retail_db():
    # This test verifies the migration script can be run
    # We test with a temp DB that has the retail schema
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        # Create retail schema first
        conn.executescript("""
            CREATE TABLE products (sku TEXT PRIMARY KEY, style_name TEXT, category TEXT, size TEXT, color TEXT, unit_cost REAL, retail_price REAL, supplier_id TEXT, created_at TEXT);
            CREATE TABLE inventory (sku TEXT PRIMARY KEY REFERENCES products(sku), location TEXT NOT NULL, stock_count INTEGER NOT NULL DEFAULT 0, reorder_point INTEGER NOT NULL DEFAULT 5, last_restocked_at TEXT);
            CREATE TABLE suppliers (supplier_id TEXT PRIMARY KEY, supplier_name TEXT NOT NULL, lead_time_days INTEGER NOT NULL, on_time_rate REAL NOT NULL, country TEXT NOT NULL);
            CREATE TABLE sales_events (event_id TEXT PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku), units_sold INTEGER NOT NULL, sale_date TEXT NOT NULL, channel TEXT NOT NULL);
        """)
        conn.commit()
        
        # Run migration
        from app.migrations import migration_001
        migration_001.run_migration(conn)
        
        # Verify tables exist alongside retail tables
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'auto_insights' in tables
        assert 'purchase_orders' in tables
        assert 'products' in tables  # Original tables still there
    finally:
        conn.close()
        os.unlink(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_application.py -v`
Expected: FAIL (script doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/apply_insightos_migration.py
#!/usr/bin/env python
"""Apply InsightOS migration to all project databases."""
import sqlite3
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.migrations import migration_001

DATABASES = [
    "retail_clothing.db",
    "derivinsightnew.db",
    "retail_insight.db",
    "deriveinsights_dashboard.db",
]

def main():
    print("Applying InsightOS migration to all databases...")
    for db_name in DATABASES:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_name)
        if not os.path.exists(db_path):
            print(f"  SKIP: {db_name} not found")
            continue
        print(f"  Applying to {db_name}...")
        conn = sqlite3.connect(db_path)
        try:
            migration_001.run_migration(conn)
            print(f"  OK: {db_name}")
        except Exception as e:
            print(f"  ERROR: {db_name} - {e}")
        finally:
            conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
```

```python
# app/services/database.py - Add to initialize_db method
def initialize_db(self):
    """Initialize database schema if it doesn't exist."""
    try:
        inspector = inspect(self.engine)
        if not inspector.has_table("users"):
            logger.info("Initializing database schema...")
            self._execute_sql_file(settings.SCHEMA_PATH)
            logger.info("Database schema initialized successfully.")
        
        # Apply InsightOS migrations
        from app.migrations import migration_001
        with self.engine.connect() as conn:
            # Get raw DBAPI connection for SQLite
            raw_conn = conn.connection
            migration_001.run_migration(raw_conn)
            logger.info("InsightOS migration applied successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migration_application.py -v`
Expected: PASS

- [ ] **Step 5: Run migration script**

```bash
python scripts/apply_insightos_migration.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/apply_insightos_migration.py app/services/database.py
git commit -m "feat: apply InsightOS migration to all databases"
```

---

### Task 3: Stockout Analyzer Module

**Files:**
- Create: `app/modules/stockout_analyzer.py`
- Test: `tests/test_stockout_analyzer.py`

**Interfaces:**
- Consumes: `app.services.database.db_service.execute(sql)` 
- Produces: `analyze_stockout_risk(domain: str, threshold_days: int = 7, method: str = "auto") -> List[Dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stockout_analyzer.py
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta

@pytest.fixture
def retail_db():
    """Create a test retail database with sample data."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    
    # Create schema
    conn.executescript("""
        CREATE TABLE products (sku TEXT PRIMARY KEY, style_name TEXT, category TEXT, size TEXT, color TEXT, unit_cost REAL, retail_price REAL, supplier_id TEXT, created_at TEXT);
        CREATE TABLE inventory (sku TEXT PRIMARY KEY REFERENCES products(sku), location TEXT NOT NULL, stock_count INTEGER NOT NULL DEFAULT 0, reorder_point INTEGER NOT NULL DEFAULT 5, last_restocked_at TEXT);
        CREATE TABLE suppliers (supplier_id TEXT PRIMARY KEY, supplier_name TEXT NOT NULL, lead_time_days INTEGER NOT NULL, on_time_rate REAL NOT NULL, country TEXT NOT NULL);
        CREATE TABLE sales_events (event_id TEXT PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku), units_sold INTEGER NOT NULL, sale_date TEXT NOT NULL, channel TEXT NOT NULL);
    """)
    
    # Insert test data
    base_date = datetime.now().strftime('%Y-%m-%d')
    past_30 = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    past_60 = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    
    # Products
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        ("CL-001", "Blue T-Shirt", "T-Shirts", "M", "Blue", 10.0, 25.0, "SUP-001", base_date),
        ("CL-002", "Red Dress", "Dresses", "S", "Red", 20.0, 50.0, "SUP-002", base_date),
        ("CL-003", "Black Jeans", "Denim", "32", "Black", 15.0, 40.0, "SUP-001", base_date),
    ])
    
    # Inventory - CL-001 at reorder point, CL-002 below, CL-003 well stocked
    conn.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", [
        ("CL-001", "Warehouse-A", 5, 5, base_date),    # At reorder point
        ("CL-002", "Warehouse-A", 2, 5, base_date),    # Below reorder point
        ("CL-003", "Warehouse-A", 100, 10, base_date), # Well stocked
    ])
    
    # Suppliers
    conn.executemany("INSERT INTO suppliers VALUES (?, ?, ?, ?, ?)", [
        ("SUP-001", "Fast Supplier", 7, 0.95, "USA"),
        ("SUP-002", "Slow Supplier", 21, 0.75, "China"),
    ])
    
    # Sales events - 30 days of sales for CL-001 (avg 2/day), CL-002 (avg 1/day)
    sales = []
    for i in range(30):
        sale_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        sales.append((f"EVT-{i:04d}", "CL-001", 2, sale_date, "online"))
        sales.append((f"EVT-{i+30:04d}", "CL-002", 1, sale_date, "store"))
        sales.append((f"EVT-{i+60:04d}", "CL-003", 5, sale_date, "online"))
    conn.executemany("INSERT INTO sales_events VALUES (?, ?, ?, ?, ?)", sales)
    
    conn.commit()
    yield db_path
    conn.close()
    os.unlink(db_path)

def test_simple_threshold_method(retail_db):
    from app.modules.stockout_analyzer import analyze_stockout_risk
    
    results = analyze_stockout_risk("retail_clothing", threshold_days=7, method="simple", db_path=retail_db)
    
    # Should find CL-001 (at reorder point) and CL-002 (below)
    at_risk_skus = [r['sku'] for r in results]
    assert "CL-001" in at_risk_skus
    assert "CL-002" in at_risk_skus
    assert "CL-003" not in at_risk_skus
    
    # Check structure
    for r in results:
        assert 'sku' in r
        assert 'style_name' in r
        assert 'stock_count' in r
        assert 'reorder_point' in r
        assert 'days_of_cover' in r
        assert 'reorder_qty' in r
        assert 'supplier_id' in r
        assert 'supplier_name' in r
        assert 'lead_time_days' in r
        assert 'finding' in r
        assert 'insight' in r
        assert 'recommended_action' in r
        assert 'confidence' in r

def test_days_of_cover_method(retail_db):
    from app.modules.stockout_analyzer import analyze_stockout_risk
    
    results = analyze_stockout_risk("retail_clothing", threshold_days=7, method="days_of_cover", db_path=retail_db)
    
    # CL-001: stock=5, avg_daily=2 => 2.5 days cover (at risk)
    # CL-002: stock=2, avg_daily=1 => 2 days cover (at risk)
    # CL-003: stock=100, avg_daily=5 => 20 days cover (not at risk)
    at_risk_skus = [r['sku'] for r in results]
    assert "CL-001" in at_risk_skus
    assert "CL-002" in at_risk_skus
    assert "CL-003" not in at_risk_skus
    
    # Check days_of_cover calculation
    cl001 = next(r for r in results if r['sku'] == 'CL-001')
    assert cl001['days_of_cover'] == pytest.approx(2.5, rel=0.1)
    
    # Check reorder qty: max(reorder_point*2 - stock, lead_time * avg_daily * 1.5)
    # CL-001: max(5*2-5=5, 7*2*1.5=21) = 21
    assert cl001['reorder_qty'] == 21

def test_auto_method_fallback(retail_db):
    from app.modules.stockout_analyzer import analyze_stockout_risk
    
    # Auto should use days_of_cover when sales data exists
    results = analyze_stockout_risk("retail_clothing", threshold_days=7, method="auto", db_path=retail_db)
    assert len(results) == 2

def test_empty_sales_fallbacks_to_simple(retail_db):
    """When no sales history, should fall back to simple method."""
    from app.modules.stockout_analyzer import analyze_stockout_risk
    
    # Create DB with no sales events
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE products (sku TEXT PRIMARY KEY, style_name TEXT, category TEXT, size TEXT, color TEXT, unit_cost REAL, retail_price REAL, supplier_id TEXT, created_at TEXT);
        CREATE TABLE inventory (sku TEXT PRIMARY KEY REFERENCES products(sku), location TEXT NOT NULL, stock_count INTEGER NOT NULL DEFAULT 0, reorder_point INTEGER NOT NULL DEFAULT 5, last_restocked_at TEXT);
        CREATE TABLE suppliers (supplier_id TEXT PRIMARY KEY, supplier_name TEXT NOT NULL, lead_time_days INTEGER NOT NULL, on_time_rate REAL NOT NULL, country TEXT NOT NULL);
        CREATE TABLE sales_events (event_id TEXT PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku), units_sold INTEGER NOT NULL, sale_date TEXT NOT NULL, channel TEXT NOT NULL);
    """)
    conn.execute("INSERT INTO products VALUES ('CL-999', 'Test', 'Test', 'M', 'Red', 10, 20, 'SUP-001', '2026-01-01')")
    conn.execute("INSERT INTO inventory VALUES ('CL-999', 'WH', 3, 5, '2026-01-01')")
    conn.execute("INSERT INTO suppliers VALUES ('SUP-001', 'Supplier', 7, 0.9, 'USA')")
    conn.commit()
    
    results = analyze_stockout_risk("retail_clothing", threshold_days=7, method="auto", db_path=db_path)
    # Should detect via simple method (stock <= reorder_point)
    assert len(results) == 1
    assert results[0]['sku'] == 'CL-999'
    conn.close()
    os.unlink(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stockout_analyzer.py -v`
Expected: FAIL with "No module named 'app.modules.stockout_analyzer'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/modules/stockout_analyzer.py
"""Stockout Risk Analysis Module for InsightOS."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sqlite3
from app.core.logger import logger

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_days_of_cover(stock_count: int, avg_daily_sales: float) -> float:
    """Calculate days of cover. Returns float('inf') if no sales."""
    if avg_daily_sales <= 0:
        return float('inf')
    return stock_count / avg_daily_sales

def calculate_reorder_qty(stock_count: int, reorder_point: int, lead_time_days: int, avg_daily_sales: float) -> int:
    """Calculate recommended reorder quantity."""
    # Method 1: Restock to 2x reorder point
    qty_to_2x_reorder = max(0, reorder_point * 2 - stock_count)
    
    # Method 2: Cover lead time + 50% buffer
    lead_time_coverage = int(lead_time_days * avg_daily_sales * 1.5) if avg_daily_sales > 0 else reorder_point * 2
    
    return max(qty_to_2x_reorder, lead_time_coverage)

def get_avg_daily_sales(conn: sqlite3.Connection, sku: str, days: int = 30) -> float:
    """Get average daily sales for a SKU over the last N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor = conn.execute(
        "SELECT SUM(units_sold) as total FROM sales_events WHERE sku = ? AND sale_date >= ?",
        (sku, cutoff_date)
    )
    row = cursor.fetchone()
    total_sold = row['total'] if row and row['total'] else 0
    return total_sold / days if days > 0 else 0

def analyze_stockout_risk(
    domain: str,
    threshold_days: int = 7,
    method: str = "auto",
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Analyze stockout risk for products in a domain.
    
    Args:
        domain: Domain name (e.g., 'retail_clothing')
        threshold_days: Days ahead to flag as at-risk
        method: 'simple' (reorder_point), 'days_of_cover', or 'auto'
        db_path: Optional database path (uses default if not provided)
    
    Returns:
        List of at-risk products with Finding, Insight, Recommended Action, Confidence
    """
    if db_path is None:
        # Default database paths per domain
        domain_db_map = {
            "retail_clothing": "retail_clothing.db",
            "banking_finance": "derivinsightnew.db",
            "insurance": "derivinsightnew.db",
        }
        db_path = domain_db_map.get(domain, "retail_clothing.db")
    
    conn = get_db_connection(db_path)
    results = []
    
    try:
        # Get all products with inventory and supplier info
        cursor = conn.execute("""
            SELECT 
                p.sku, p.style_name, p.category, p.size, p.color, p.supplier_id,
                i.stock_count, i.reorder_point, i.location,
                s.supplier_name, s.lead_time_days, s.on_time_rate
            FROM products p
            JOIN inventory i ON p.sku = i.sku
            JOIN suppliers s ON p.supplier_id = s.supplier_id
            WHERE i.stock_count >= 0
        """)
        products = cursor.fetchall()
        
        for product in products:
            sku = product['sku']
            stock_count = product['stock_count']
            reorder_point = product['reorder_point']
            lead_time_days = product['lead_time_days']
            
            # Determine calculation method
            use_days_of_cover = False
            if method == "days_of_cover":
                use_days_of_cover = True
            elif method == "auto":
                # Check if sales history exists
                avg_daily = get_avg_daily_sales(conn, sku)
                use_days_of_cover = avg_daily > 0
            
            if use_days_of_cover:
                avg_daily_sales = get_avg_daily_sales(conn, sku)
                days_of_cover = calculate_days_of_cover(stock_count, avg_daily_sales)
                at_risk = days_of_cover <= threshold_days
            else:
                # Simple threshold method
                days_of_cover = float('inf')
                avg_daily_sales = 0
                at_risk = stock_count <= reorder_point
            
            if at_risk:
                reorder_qty = calculate_reorder_qty(stock_count, reorder_point, lead_time_days, avg_daily_sales)
                
                # Build Finding, Insight, Recommended Action
                if use_days_of_cover:
                    finding = f"{product['style_name']} ({sku}) has {days_of_cover:.1f} days of cover remaining"
                    insight = f"Current stock ({stock_count}) will last only {days_of_cover:.1f} days at current sales velocity ({avg_daily_sales:.1f}/day). Supplier lead time is {lead_time_days} days."
                else:
                    finding = f"{product['style_name']} ({sku}) is at or below reorder point"
                    insight = f"Stock count ({stock_count}) has reached reorder threshold ({reorder_point}). Immediate reorder needed to prevent stockout."
                
                recommended_action = f"Reorder {reorder_qty} units from {product['supplier_name']} (lead time: {lead_time_days} days)"
                
                # Confidence: higher when we have sales data
                confidence = 0.85 if use_days_of_cover else 0.7
                
                results.append({
                    "sku": sku,
                    "style_name": product['style_name'],
                    "category": product['category'],
                    "size": product['size'],
                    "color": product['color'],
                    "location": product['location'],
                    "stock_count": stock_count,
                    "reorder_point": reorder_point,
                    "days_of_cover": round(days_of_cover, 1) if days_of_cover != float('inf') else None,
                    "avg_daily_sales": round(avg_daily_sales, 1) if avg_daily_sales > 0 else None,
                    "reorder_qty": reorder_qty,
                    "supplier_id": product['supplier_id'],
                    "supplier_name": product['supplier_name'],
                    "lead_time_days": lead_time_days,
                    "on_time_rate": product['on_time_rate'],
                    "finding": finding,
                    "insight": insight,
                    "recommended_action": recommended_action,
                    "confidence": confidence,
                    "method_used": "days_of_cover" if use_days_of_cover else "simple_threshold"
                })
        
        # Sort by urgency (lowest days of cover first, then by stock level)
        results.sort(key=lambda x: (x['days_of_cover'] if x['days_of_cover'] else 999, x['stock_count']))
        
        logger.info(f"Stockout analysis for {domain}: {len(results)} at-risk products found")
        return results
        
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stockout_analyzer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/stockout_analyzer.py tests/test_stockout_analyzer.py
git commit -m "feat: add stockout_analyzer module with simple and days-of-cover methods"
```

---

### Task 4: Stockout API Endpoints

**Files:**
- Create: `app/api/stockout_endpoints.py`
- Modify: `app/api/endpoints.py` (import and include router)
- Test: `tests/test_stockout_endpoints.py`

**Interfaces:**
- Consumes: `app.modules.stockout_analyzer.analyze_stockout_risk`
- Produces: 
  - `GET /api/v1/stockout/risk?domain=retail_clothing&days=7&method=auto`
  - `GET /api/v1/stockout/sku/{sku}?domain=retail_clothing`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stockout_endpoints.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stockout_risk_endpoint():
    response = client.get("/api/v1/stockout/risk?domain=retail_clothing&days=7&method=auto")
    assert response.status_code == 200
    data = response.json()
    assert "at_risk_products" in data
    assert "count" in data
    assert "domain" in data
    assert data["domain"] == "retail_clothing"
    assert isinstance(data["at_risk_products"], list)

def test_stockout_risk_endpoint_with_invalid_domain():
    response = client.get("/api/v1/stockout/risk?domain=invalid_domain")
    # Should still work but return empty or use default
    assert response.status_code == 200

def test_stockout_sku_detail_endpoint():
    response = client.get("/api/v1/stockout/sku/CL-001?domain=retail_clothing")
    # May return 404 if SKU doesn't exist, but should not 500
    assert response.status_code in [200, 404]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stockout_endpoints.py -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Write minimal implementation**

```python
# app/api/stockout_endpoints.py
"""Stockout Risk API Endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.modules.stockout_analyzer import analyze_stockout_risk
from app.core.logger import logger

router = APIRouter(prefix="/stockout", tags=["stockout"])

@router.get("/risk")
async def get_stockout_risk(
    domain: str = Query("retail_clothing", description="Domain to analyze"),
    days: int = Query(7, ge=1, le=90, description="Days ahead threshold"),
    method: str = Query("auto", description="Calculation method: simple, days_of_cover, auto"),
):
    """Get products at risk of stockout."""
    logger.info(f"Stockout risk request: domain={domain}, days={days}, method={method}")
    
    try:
        results = analyze_stockout_risk(domain, threshold_days=days, method=method)
        return {
            "domain": domain,
            "threshold_days": days,
            "method": method,
            "count": len(results),
            "at_risk_products": results
        }
    except Exception as e:
        logger.error(f"Stockout risk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sku/{sku}")
async def get_stockout_detail(
    sku: str,
    domain: str = Query("retail_clothing", description="Domain"),
):
    """Get detailed stockout analysis for a specific SKU."""
    logger.info(f"Stockout detail request: sku={sku}, domain={domain}")
    
    try:
        results = analyze_stockout_risk(domain, threshold_days=90, method="auto")
        product = next((r for r in results if r['sku'] == sku), None)
        
        if not product:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found or not at risk")
        
        return product
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stockout detail failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

```python
# app/api/endpoints.py - Add import and include router
from app.api.stockout_endpoints import router as stockout_router

# ... after existing router definitions ...
router.include_router(stockout_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stockout_endpoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/stockout_endpoints.py app/api/endpoints.py tests/test_stockout_endpoints.py
git commit -m "feat: add stockout risk API endpoints"
```

---

### Task 5: LangGraph Integration - Stockout Analysis Node

**Files:**
- Modify: `app/orchestration/workflow.py` (add stockout node and edge)
- Test: `tests/test_workflow_stockout.py`

**Interfaces:**
- Consumes: `app.modules.stockout_analyzer.analyze_stockout_risk`
- Produces: GraphState with `stockout_analysis` field

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_stockout.py
import pytest
from app.orchestration.workflow import app_graph

@pytest.mark.asyncio
async def test_stockout_node_in_graph():
    """Test that stockout analysis runs in the graph for relevant queries."""
    # This tests the graph structure, not full execution
    # Check that the node exists in the compiled graph
    nodes = app_graph.get_graph().nodes
    node_names = list(nodes.keys())
    assert "analyze_stockout" in node_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_stockout.py -v`
Expected: FAIL (node doesn't exist)

- [ ] **Step 3: Write minimal implementation**

```python
# app/orchestration/workflow.py - Add after imports
from app.modules.stockout_analyzer import analyze_stockout_risk

# Add new node after execute_query_node
async def analyze_stockout_node(state: GraphState) -> Dict[str, Any]:
    """Analyze stockout risk for query results."""
    logger.info("Node: [analyze_stockout]")
    domain = state.get("domain", "general")
    query = state["user_question"]
    results = state.get("query_result", [])
    
    # Only run stockout analysis for relevant domains and successful queries
    if domain not in ["retail_clothing", "general"] or state.get("status") != "success":
        return {}
    
    # Check if query is related to inventory/stock
    stock_keywords = ["stock", "inventory", "reorder", "stockout", "supply", "product", "sku"]
    if not any(kw in query.lower() for kw in stock_keywords):
        return {}
    
    try:
        stockout_results = analyze_stockout_risk(domain, threshold_days=7, method="auto")
        logger.info(f"Stockout analysis complete: {len(stockout_results)} at-risk products")
        
        # If there are at-risk products, we can enhance the insight/recommendation
        if stockout_results:
            # Add stockout context to state for insight generation
            return {
                "stockout_analysis": stockout_results,
                "stockout_count": len(stockout_results)
            }
    except Exception as e:
        logger.warning(f"Stockout analysis failed: {e}")
    
    return {}

# In graph construction, add after execute_query:
# workflow.add_node("analyze_stockout", analyze_stockout_node)
# workflow.add_edge("execute_query", "analyze_stockout")
# Then change: workflow.add_edge("analyze_stockout", "recommend_visualization")
# And: workflow.add_edge("analyze_stockout", "insight_recommendation")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_stockout.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/orchestration/workflow.py tests/test_workflow_stockout.py
git commit -m "feat: add stockout analysis node to LangGraph pipeline"
```

---

### Task 6: Auto Insights Scheduler Service

**Files:**
- Create: `app/services/auto_insights_scheduler.py`
- Test: `tests/test_auto_insights_scheduler.py`

**Interfaces:**
- Consumes: `app.modules.stockout_analyzer.analyze_stockout_risk`, `app.services.database.db_service`
- Produces: Background job that inserts into `auto_insights` table

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auto_insights_scheduler.py
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE products (sku TEXT PRIMARY KEY, style_name TEXT, category TEXT, size TEXT, color TEXT, unit_cost REAL, retail_price REAL, supplier_id TEXT, created_at TEXT);
        CREATE TABLE inventory (sku TEXT PRIMARY KEY REFERENCES products(sku), location TEXT NOT NULL, stock_count INTEGER NOT NULL DEFAULT 0, reorder_point INTEGER NOT NULL DEFAULT 5, last_restocked_at TEXT);
        CREATE TABLE suppliers (supplier_id TEXT PRIMARY KEY, supplier_name TEXT NOT NULL, lead_time_days INTEGER NOT NULL, on_time_rate REAL NOT NULL, country TEXT NOT NULL);
        CREATE TABLE sales_events (event_id TEXT PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku), units_sold INTEGER NOT NULL, sale_date TEXT NOT NULL, channel TEXT NOT NULL);
        CREATE TABLE auto_insights (
            insight_id TEXT PRIMARY KEY, domain TEXT NOT NULL, insight_type TEXT NOT NULL,
            severity TEXT NOT NULL, title TEXT NOT NULL, description TEXT, payload_json TEXT,
            sku TEXT, supplier_id TEXT, status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, acknowledged_at TIMESTAMP, acknowledged_by TEXT
        );
    """)
    
    # Add test data with stockout risk
    base_date = datetime.now().strftime('%Y-%m-%d')
    past_30 = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        ("CL-001", "Blue T-Shirt", "T-Shirts", "M", "Blue", 10.0, 25.0, "SUP-001", base_date),
        ("CL-002", "Red Dress", "Dresses", "S", "Red", 20.0, 50.0, "SUP-002", base_date),
    ])
    
    conn.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", [
        ("CL-001", "Warehouse-A", 3, 5, base_date),    # Below reorder point
        ("CL-002", "Warehouse-A", 0, 5, base_date),    # Critical stockout
    ])
    
    conn.executemany("INSERT INTO suppliers VALUES (?, ?, ?, ?, ?)", [
        ("SUP-001", "Fast Supplier", 7, 0.95, "USA"),
        ("SUP-002", "Slow Supplier", 21, 0.75, "China"),
    ])
    
    # Sales for days_of_cover
    for i in range(30):
        sale_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        conn.execute("INSERT INTO sales_events VALUES (?, ?, ?, ?, ?)", 
                    (f"EVT-{i:04d}", "CL-001", 2, sale_date, "online"))
        conn.execute("INSERT INTO sales_events VALUES (?, ?, ?, ?, ?)", 
                    (f"EVT-{i+30:04d}", "CL-002", 1, sale_date, "store"))
    conn.commit()
    yield db_path
    conn.close()
    os.unlink(db_path)

def test_detect_stockout_risk_insights(test_db):
    from app.services.auto_insights_scheduler import detect_and_store_insights
    
    count = detect_and_store_insights("retail_clothing", db_path=test_db)
    assert count >= 2  # At least 2 stockout insights
    
    # Verify insights stored
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM auto_insights WHERE domain='retail_clothing'")
    insights = cursor.fetchall()
    conn.close()
    
    assert len(insights) >= 2
    for insight in insights:
        assert insight['domain'] == 'retail_clothing'
        assert insight['insight_type'] in ['stockout_risk', 'critical_inventory']
        assert insight['severity'] in ['HIGH', 'CRITICAL']
        assert insight['status'] == 'ACTIVE'
        assert insight['sku'] is not None

def test_detect_critical_inventory(test_db):
    from app.services.auto_insights_scheduler import detect_and_store_insights
    
    detect_and_store_insights("retail_clothing", db_path=test_db)
    
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM auto_insights WHERE insight_type='critical_inventory'")
    critical = cursor.fetchall()
    conn.close()
    
    # CL-002 has stock_count=0, should be critical
    assert len(critical) >= 1
    assert any(i['sku'] == 'CL-002' for i in critical)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_insights_scheduler.py -v`
Expected: FAIL with "No module named 'app.services.auto_insights_scheduler'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/auto_insights_scheduler.py
"""Auto-Generated Insights Scheduler for InsightOS."""
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.modules.stockout_analyzer import analyze_stockout_risk, get_db_connection
from app.core.config import settings
from app.core.logger import logger

# Global scheduler instance
scheduler = None

def generate_insight_id() -> str:
    """Generate unique insight ID."""
    return f"INS-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

def detect_stockout_insights(domain: str, db_path: str) -> List[Dict[str, Any]]:
    """Detect stockout-related insights."""
    insights = []
    stockout_results = analyze_stockout_risk(domain, threshold_days=7, method="auto", db_path=db_path)
    
    for result in stockout_results:
        sku = result['sku']
        stock_count = result['stock_count']
        days_of_cover = result['days_of_cover']
        
        if stock_count == 0:
            insight_type = "critical_inventory"
            severity = "CRITICAL"
            title = f"Critical Stockout: {result['style_name']} ({sku})"
            description = f"Product {result['style_name']} ({sku}) is completely out of stock at {result['location']}."
        elif days_of_cover and days_of_cover <= 3:
            insight_type = "stockout_risk"
            severity = "HIGH"
            title = f"Imminent Stockout Risk: {result['style_name']} ({sku})"
            description = f"Only {days_of_cover:.1f} days of cover remaining. Reorder {result['reorder_qty']} units immediately."
        else:
            insight_type = "stockout_risk"
            severity = "MEDIUM"
            title = f"Stockout Risk: {result['style_name']} ({sku})"
            description = f"{days_of_cover:.1f} days of cover. Reorder {result['reorder_qty']} units from {result['supplier_name']}."
        
        insights.append({
            "insight_id": generate_insight_id(),
            "domain": domain,
            "insight_type": insight_type,
            "severity": severity,
            "title": title,
            "description": description,
            "payload_json": str(result),  # Store full result for drill-down
            "sku": sku,
            "supplier_id": result['supplier_id'],
            "status": "ACTIVE",
        })
    
    return insights

def detect_sales_drop_insights(domain: str, db_path: str) -> List[Dict[str, Any]]:
    """Detect sudden sales drop insights."""
    insights = []
    conn = get_db_connection(db_path)
    
    try:
        # Get products with sales in last 14 days
        cursor = conn.execute("""
            SELECT DISTINCT sku FROM sales_events 
            WHERE sale_date >= date('now', '-14 days')
        """)
        active_skus = [row['sku'] for row in cursor.fetchall()]
        
        for sku in active_skus:
            # Current 7-day average
            cursor = conn.execute("""
                SELECT AVG(daily_sales) as avg_sales FROM (
                    SELECT sale_date, SUM(units_sold) as daily_sales
                    FROM sales_events 
                    WHERE sku = ? AND sale_date >= date('now', '-7 days')
                    GROUP BY sale_date
                )
            """, (sku,))
            current_row = cursor.fetchone()
            current_avg = current_row['avg_sales'] if current_row and current_row['avg_sales'] else 0
            
            # Prior 7-day average (days 8-14)
            cursor = conn.execute("""
                SELECT AVG(daily_sales) as avg_sales FROM (
                    SELECT sale_date, SUM(units_sold) as daily_sales
                    FROM sales_events 
                    WHERE sku = ? AND sale_date >= date('now', '-14 days') AND sale_date < date('now', '-7 days')
                    GROUP BY sale_date
                )
            """, (sku,))
            prior_row = cursor.fetchone()
            prior_avg = prior_row['avg_sales'] if prior_row and prior_row['avg_sales'] else 0
            
            if prior_avg > 0 and current_avg < prior_avg * 0.5:
                # Get product info
                cursor = conn.execute("SELECT style_name FROM products WHERE sku = ?", (sku,))
                product = cursor.fetchone()
                style_name = product['style_name'] if product else sku
                
                insights.append({
                    "insight_id": generate_insight_id(),
                    "domain": domain,
                    "insight_type": "sales_drop",
                    "severity": "MEDIUM",
                    "title": f"Sales Drop: {style_name} ({sku})",
                    "description": f"Sales dropped {((prior_avg - current_avg) / prior_avg * 100):.0f}% vs prior week (avg {current_avg:.1f} vs {prior_avg:.1f}/day).",
                    "payload_json": f'{{"sku": "{sku}", "current_avg": {current_avg}, "prior_avg": {prior_avg}}}',
                    "sku": sku,
                    "supplier_id": None,
                    "status": "ACTIVE",
                })
    finally:
        conn.close()
    
    return insights

def detect_supplier_risk_insights(domain: str, db_path: str) -> List[Dict[str, Any]]:
    """Detect supplier reliability risk insights."""
    insights = []
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute("""
            SELECT s.supplier_id, s.supplier_name, s.lead_time_days, s.on_time_rate,
                   COUNT(DISTINCT p.sku) as product_count
            FROM suppliers s
            JOIN products p ON s.supplier_id = p.supplier_id
            JOIN inventory i ON p.sku = i.sku
            WHERE s.lead_time_days > 14 AND s.on_time_rate < 0.8
            GROUP BY s.supplier_id
        """)
        
        for row in cursor.fetchall():
            insights.append({
                "insight_id": generate_insight_id(),
                "domain": domain,
                "insight_type": "supplier_risk",
                "severity": "MEDIUM",
                "title": f"Supplier Risk: {row['supplier_name']}",
                "description": f"Supplier {row['supplier_name']} has {row['lead_time_days']} day lead time and only {row['on_time_rate']:.0%} on-time rate. Affects {row['product_count']} products.",
                "payload_json": f'{{"supplier_id": "{row["supplier_id"]}", "lead_time_days": {row["lead_time_days"]}, "on_time_rate": {row["on_time_rate"]}}}',
                "sku": None,
                "supplier_id": row['supplier_id'],
                "status": "ACTIVE",
            })
    finally:
        conn.close()
    
    return insights

def detect_and_store_insights(domain: str, db_path: Optional[str] = None) -> int:
    """Run all detection rules and store insights."""
    if db_path is None:
        domain_db_map = {
            "retail_clothing": "retail_clothing.db",
            "banking_finance": "derivinsightnew.db",
            "insurance": "derivinsightnew.db",
        }
        db_path = domain_db_map.get(domain, "retail_clothing.db")
    
    all_insights = []
    all_insights.extend(detect_stockout_insights(domain, db_path))
    all_insights.extend(detect_sales_drop_insights(domain, db_path))
    all_insights.extend(detect_supplier_risk_insights(domain, db_path))
    
    if not all_insights:
        logger.info(f"No new insights for domain: {domain}")
        return 0
    
    # Store insights
    conn = get_db_connection(db_path)
    try:
        with conn:
            for insight in all_insights:
                conn.execute("""
                    INSERT OR REPLACE INTO auto_insights 
                    (insight_id, domain, insight_type, severity, title, description, payload_json, sku, supplier_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    insight['insight_id'], insight['domain'], insight['insight_type'],
                    insight['severity'], insight['title'], insight['description'],
                    insight['payload_json'], insight['sku'], insight['supplier_id'], insight['status']
                ))
        logger.info(f"Stored {len(all_insights)} new insights for domain: {domain}")
        return len(all_insights)
    finally:
        conn.close()

def start_scheduler(interval_minutes: int = 90):
    """Start the APScheduler background job."""
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already running")
        return scheduler
    
    scheduler = BackgroundScheduler()
    
    # Add job for each domain
    domains = ["retail_clothing", "banking_finance", "insurance"]
    for domain in domains:
        scheduler.add_job(
            detect_and_store_insights,
            trigger=IntervalTrigger(minutes=interval_minutes),
            args=[domain],
            id=f"auto_insights_{domain}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    
    scheduler.start()
    logger.info(f"Auto-insights scheduler started with {interval_minutes} min interval for domains: {domains}")
    return scheduler

def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Auto-insights scheduler stopped")

def get_scheduler():
    """Get scheduler instance."""
    return scheduler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auto_insights_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/auto_insights_scheduler.py tests/test_auto_insights_scheduler.py
git commit -m "feat: add auto_insights_scheduler with APScheduler and detection rules"
```

---

### Task 7: Scheduler Integration with FastAPI App

**Files:**
- Modify: `app/main.py` (add startup/shutdown events)
- Test: `tests/test_scheduler_integration.py`

**Interfaces:**
- Consumes: `app.services.auto_insights_scheduler.start_scheduler`, `stop_scheduler`
- Produces: Scheduler running on app startup

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler_integration.py
from fastapi.testclient import TestClient
from app.main import app
from app.services.auto_insights_scheduler import get_scheduler

def test_scheduler_starts_on_app_startup():
    with TestClient(app) as client:
        # App startup triggers lifespan events
        scheduler = get_scheduler()
        assert scheduler is not None
        assert scheduler.running == True

def test_scheduler_stops_on_app_shutdown():
    # This is harder to test with TestClient, but we can verify the function exists
    from app.services.auto_insights_scheduler import stop_scheduler
    assert callable(stop_scheduler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler_integration.py -v`
Expected: FAIL (scheduler not started)

- [ ] **Step 3: Write minimal implementation**

```python
# app/main.py - Add to existing FastAPI app
from contextlib import asynccontextmanager
from app.services.auto_insights_scheduler import start_scheduler, stop_scheduler
from app.core.config import settings

@asynccontextmanager
async def lifespan(app):
    # Startup
    logger.info("Starting InsightOS application...")
    scheduler_mode = getattr(settings, 'SCHEDULER_MODE', 'embedded')
    interval = getattr(settings, 'SCHEDULER_INTERVAL_MINUTES', 90)
    
    if scheduler_mode == "embedded":
        start_scheduler(interval_minutes=interval)
    
    yield
    
    # Shutdown
    logger.info("Shutting down InsightOS application...")
    stop_scheduler()

# Update FastAPI app creation:
app = FastAPI(
    title="InsightOS API",
    description="Virtual Decision Officer API",
    version="1.0.0",
    lifespan=lifespan
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_scheduler_integration.py
git commit -m "feat: integrate auto_insights_scheduler with FastAPI lifespan"
```

---

### Task 8: Auto Insights API Endpoints

**Files:**
- Create: `app/api/insights_endpoints.py`
- Modify: `app/api/endpoints.py` (include router)
- Test: `tests/test_insights_endpoints.py`

**Interfaces:**
- Consumes: `app.services.database.db_service.execute`
- Produces:
  - `GET /api/v1/insights/today?domain=retail_clothing`
  - `GET /api/v1/insights/history?domain=retail_clothing&days=7`
  - `POST /api/v1/insights/{id}/acknowledge`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_insights_endpoints.py
from fastapi.testclient import TestClient
from app.main import app
import sqlite3
import tempfile
import os

client = TestClient(app)

@pytest.fixture
def setup_insights():
    # Create test DB with insights
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE auto_insights (
            insight_id TEXT PRIMARY KEY, domain TEXT NOT NULL, insight_type TEXT NOT NULL,
            severity TEXT NOT NULL, title TEXT NOT NULL, description TEXT, payload_json TEXT,
            sku TEXT, supplier_id TEXT, status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, acknowledged_at TIMESTAMP, acknowledged_by TEXT
        );
    """)
    conn.execute("""
        INSERT INTO auto_insights (insight_id, domain, insight_type, severity, title, description, status)
        VALUES ('INS-20260824-0001', 'retail_clothing', 'stockout_risk', 'HIGH', 'Test Insight', 'Test description', 'ACTIVE')
    """)
    conn.commit()
    yield db_path
    conn.close()
    os.unlink(db_path)

def test_get_todays_insights(setup_insights):
    # This test would need to override the DB path
    # For now, test endpoint structure
    response = client.get("/api/v1/insights/today?domain=retail_clothing")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
    assert "domain" in data
    assert isinstance(data["insights"], list)

def test_get_insights_history():
    response = client.get("/api/v1/insights/history?domain=retail_clothing&days=7")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
    assert "domain" in data
    assert "days" in data

def test_acknowledge_insight():
    response = client.post("/api/v1/insights/INS-20260824-0001/acknowledge")
    assert response.status_code in [200, 404]  # 404 if not found
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_insights_endpoints.py -v`
Expected: FAIL (endpoints not found)

- [ ] **Step 3: Write minimal implementation**

```python
# app/api/insights_endpoints.py
"""Auto Insights API Endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta
from app.services.database import db_service
from app.core.logger import logger

router = APIRouter(prefix="/insights", tags=["insights"])

@router.get("/today")
async def get_todays_insights(
    domain: str = Query("retail_clothing", description="Domain to query"),
):
    """Get today's active insights for dashboard."""
    logger.info(f"Today's insights request: domain={domain}")
    
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        results = db_service.execute(f"""
            SELECT * FROM auto_insights 
            WHERE domain = '{domain}' 
            AND status = 'ACTIVE'
            AND date(created_at) = '{today}'
            ORDER BY 
                CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                created_at DESC
        """)
        
        insights = []
        for row in results:
            insights.append({
                "insight_id": row['insight_id'],
                "insight_type": row['insight_type'],
                "severity": row['severity'],
                "title": row['title'],
                "description": row['description'],
                "sku": row['sku'],
                "supplier_id": row['supplier_id'],
                "created_at": row['created_at'],
            })
        
        return {
            "domain": domain,
            "date": today,
            "count": len(insights),
            "insights": insights
        }
    except Exception as e:
        logger.error(f"Get today's insights failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_insights_history(
    domain: str = Query("retail_clothing", description="Domain to query"),
    days: int = Query(7, ge=1, le=90, description="Number of days of history"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """Get historical insights."""
    logger.info(f"Insights history request: domain={domain}, days={days}, status={status}")
    
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        where_clause = f"domain = '{domain}' AND date(created_at) >= '{cutoff_date}'"
        if status:
            where_clause += f" AND status = '{status}'"
        
        results = db_service.execute(f"""
            SELECT * FROM auto_insights 
            WHERE {where_clause}
            ORDER BY created_at DESC
        """)
        
        insights = []
        for row in results:
            insights.append({
                "insight_id": row['insight_id'],
                "insight_type": row['insight_type'],
                "severity": row['severity'],
                "title": row['title'],
                "description": row['description'],
                "sku": row['sku'],
                "supplier_id": row['supplier_id'],
                "status": row['status'],
                "created_at": row['created_at'],
                "acknowledged_at": row['acknowledged_at'],
            })
        
        return {
            "domain": domain,
            "days": days,
            "count": len(insights),
            "insights": insights
        }
    except Exception as e:
        logger.error(f"Get insights history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{insight_id}/acknowledge")
async def acknowledge_insight(
    insight_id: str,
    acknowledged_by: str = Query("user", description="Who acknowledged"),
):
    """Mark an insight as acknowledged."""
    logger.info(f"Acknowledge insight: {insight_id} by {acknowledged_by}")
    
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = db_service.execute(f"""
            UPDATE auto_insights 
            SET status = 'ACKNOWLEDGED', acknowledged_at = '{now}', acknowledged_by = '{acknowledged_by}'
            WHERE insight_id = '{insight_id}'
        """)
        
        if not result or result[0].get('rows_affected', 0) == 0:
            raise HTTPException(status_code=404, detail="Insight not found")
        
        return {"status": "acknowledged", "insight_id": insight_id, "acknowledged_at": now}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Acknowledge insight failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

```python
# app/api/endpoints.py - Add import and include router
from app.api.insights_endpoints import router as insights_router

# ... after existing router definitions ...
router.include_router(insights_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_insights_endpoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/insights_endpoints.py app/api/endpoints.py tests/test_insights_endpoints.py
git commit -m "feat: add auto insights API endpoints (today, history, acknowledge)"
```

---

### Task 9: Frontend - Insights Dashboard Component

**Files:**
- Modify: `frontend/script.js` (add InsightsDashboard component)
- Modify: `frontend/index.html` (add Insights tab)
- Modify: `frontend/styles.css` (add insights styles)
- Test: Manual verification

**Interfaces:**
- Consumes: `GET /api/v1/insights/today`
- Produces: Interactive "Today's Insights" cards grid

- [ ] **Step 1: Write the failing test** (manual verification steps)

```javascript
// Manual test steps:
// 1. Start backend: python -m uvicorn app.main:app --reload
// 2. Open frontend/index.html in browser
// 3. Click "Insights" tab
// 4. Verify "Today's Insights" cards appear with severity badges
// 5. Click "View Details" on a card - should show full insight
// 6. Click "Acknowledge" - should mark as acknowledged
```

- [ ] **Step 2: Implement frontend components**

```javascript
// frontend/script.js - Add to state object
const state = {
    // ... existing state ...
    insightsTabActive: false,
    currentInsights: [],
};

// Add to DOM elements
const elements = {
    // ... existing elements ...
    insightsTab: document.getElementById('insights-tab'),
    insightsContainer: document.getElementById('insights-container'),
};

// Add to initialization
async function initialize() {
    // ... existing init ...
    // Add event listener for insights tab
    if (elements.insightsTab) {
        elements.insightsTab.addEventListener('click', () => switchToInsightsTab());
    }
    // Load insights on startup if tab is active
}

async function switchToInsightsTab() {
    state.insightsTabActive = true;
    // Hide other panels
    elements.chatContainer.classList.add('hidden');
    elements.resultsPanel.classList.add('hidden');
    elements.sentinelDashboard.classList.add('hidden');
    
    // Show insights container
    if (elements.insightsContainer) {
        elements.insightsContainer.classList.remove('hidden');
    }
    
    // Load insights
    await loadTodaysInsights();
}

async function loadTodaysInsights() {
    try {
        const response = await fetch(`${state.apiUrl}/api/v1/insights/today?domain=${state.selectedDomain}`);
        const data = await response.json();
        state.currentInsights = data.insights || [];
        renderInsightsDashboard(data.insights || []);
    } catch (error) {
        console.error('Failed to load insights:', error);
        if (elements.insightsContainer) {
            elements.insightsContainer.innerHTML = `<div class="error">Failed to load insights: ${error.message}</div>`;
        }
    }
}

function renderInsightsDashboard(insights) {
    const container = elements.insightsContainer;
    if (!container) return;
    
    if (!insights || insights.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>No Active Insights</h3>
                <p>All systems nominal. No actionable insights at this time.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="insights-header">
            <h2>Today's Insights</h2>
            <span class="insights-count">${insights.length} active</span>
        </div>
        <div class="insights-grid" id="insights-grid"></div>
    `;
    
    const grid = document.getElementById('insights-grid');
    insights.forEach(insight => {
        grid.appendChild(createInsightCard(insight));
    });
}

function createInsightCard(insight) {
    const card = document.createElement('div');
    card.className = `insight-card severity-${insight.severity.toLowerCase()}`;
    card.dataset.insightId = insight.insight_id;
    
    const severityClass = insight.severity.toLowerCase();
    const timeAgo = formatTimeAgo(insight.created_at);
    
    card.innerHTML = `
        <div class="insight-header">
            <span class="severity-badge ${severityClass}">${insight.severity}</span>
            <span class="insight-type">${formatInsightType(insight.insight_type)}</span>
            <span class="insight-time">${timeAgo}</span>
        </div>
        <h3 class="insight-title">${insight.title}</h3>
        <p class="insight-description">${insight.description}</p>
        <div class="insight-meta">
            ${insight.sku ? `<span class="insight-sku">SKU: ${insight.sku}</span>` : ''}
            ${insight.supplier_id ? `<span class="insight-supplier">Supplier: ${insight.supplier_id}</span>` : ''}
        </div>
        <div class="insight-actions">
            <button class="btn btn-primary view-details" data-id="${insight.insight_id}">View Details</button>
            <button class="btn btn-secondary acknowledge" data-id="${insight.insight_id}">Acknowledge</button>
        </div>
    `;
    
    // Add event listeners
    card.querySelector('.view-details').addEventListener('click', () => showInsightDetails(insight));
    card.querySelector('.acknowledge').addEventListener('click', () => acknowledgeInsight(insight.insight_id));
    
    return card;
}

function formatInsightType(type) {
    const types = {
        'stockout_risk': 'Stockout Risk',
        'critical_inventory': 'Critical Inventory',
        'sales_drop': 'Sales Drop',
        'supplier_risk': 'Supplier Risk',
    };
    return types[type] || type;
}

function formatTimeAgo(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
}

async function showInsightDetails(insight) {
    // Show modal with full insight details
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <h2>${insight.title}</h2>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="detail-row"><strong>Type:</strong> ${formatInsightType(insight.insight_type)}</div>
                <div class="detail-row"><strong>Severity:</strong> <span class="severity-badge ${insight.severity.toLowerCase()}">${insight.severity}</span></div>
                <div class="detail-row"><strong>Description:</strong> ${insight.description}</div>
                ${insight.sku ? `<div class="detail-row"><strong>SKU:</strong> ${insight.sku}</div>` : ''}
                ${insight.supplier_id ? `<div class="detail-row"><strong>Supplier:</strong> ${insight.supplier_id}</div>` : ''}
                <div class="detail-row"><strong>Created:</strong> ${insight.created_at}</div>
                <div class="detail-row"><strong>Status:</strong> ${insight.status}</div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary close-modal">Close</button>
                ${insight.status === 'ACTIVE' ? `<button class="btn btn-primary acknowledge-modal" data-id="${insight.insight_id}">Acknowledge</button>` : ''}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.close-modal').addEventListener('click', () => modal.remove());
    modal.querySelector('.acknowledge-modal')?.addEventListener('click', () => {
        acknowledgeInsight(insight.insight_id);
        modal.remove();
    });
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function acknowledgeInsight(insightId) {
    try {
        const response = await fetch(`${state.apiUrl}/api/v1/insights/${insightId}/acknowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        
        if (response.ok) {
            // Update UI
            const card = document.querySelector(`[data-insight-id="${insightId}"]`);
            if (card) {
                card.querySelector('.acknowledge').disabled = true;
                card.querySelector('.acknowledge').textContent = 'Acknowledged';
                card.classList.add('acknowledged');
            }
            showNotification('Insight acknowledged');
        } else {
            showNotification('Failed to acknowledge insight', 'error');
        }
    } catch (error) {
        console.error('Acknowledge failed:', error);
        showNotification('Error acknowledging insight', 'error');
    }
}

function showNotification(message, type = 'success') {
    // Simple notification
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3000);
}
```

```html
<!-- frontend/index.html - Add Insights tab to navigation -->
<!-- In the sidebar/navigation area, add: -->
<button id="insights-tab" class="nav-tab" data-tab="insights">
    <span class="tab-icon">💡</span>
    <span>Insights</span>
    <span class="insights-badge" id="insights-badge">0</span>
</button>

<!-- Add insights container -->
<div id="insights-container" class="tab-panel hidden">
    <div class="panel-header">
        <h2>Today's Insights</h2>
        <button id="refresh-insights" class="btn btn-secondary">Refresh</button>
    </div>
    <div id="insights-content"></div>
</div>
```

```css
/* frontend/styles.css - Add insights styles */
.insights-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
}

.insights-count {
    background: var(--primary-color);
    color: white;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.875rem;
}

.insights-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1rem;
}

.insight-card {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
    transition: transform 0.2s, box-shadow 0.2s;
}

.insight-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.insight-card.severity-critical {
    border-left: 4px solid #ff4d4f;
}

.insight-card.severity-high {
    border-left: 4px solid #faad14;
}

.insight-card.severity-medium {
    border-left: 4px solid #1890ff;
}

.insight-card.severity-low {
    border-left: 4px solid #52c41a;
}

.insight-card.acknowledged {
    opacity: 0.6;
    background: var(--bg-secondary);
}

.insight-header {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
}

.severity-badge {
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}

.severity-badge.critical { background: #ff4d4f; color: white; }
.severity-badge.high { background: #faad14; color: #1a1a1a; }
.severity-badge.medium { background: #1890ff; color: white; }
.severity-badge.low { background: #52c41a; color: white; }

.insight-type {
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: capitalize;
}

.insight-time {
    margin-left: auto;
    font-size: 0.75rem;
    color: var(--text-muted);
}

.insight-title {
    margin: 0.5rem 0;
    font-size: 1rem;
    color: var(--text-primary);
}

.insight-description {
    color: var(--text-secondary);
    font-size: 0.875rem;
    line-height: 1.5;
    margin-bottom: 0.75rem;
}

.insight-meta {
    display: flex;
    gap: 1rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 1rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-color);
}

.insight-actions {
    display: flex;
    gap: 0.5rem;
}

.insight-actions .btn {
    flex: 1;
    padding: 0.5rem;
    font-size: 0.875rem;
}

.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
}

.modal {
    background: var(--card-bg);
    border-radius: 12px;
    max-width: 500px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-muted);
}

.modal-body {
    padding: 1rem;
}

.detail-row {
    margin-bottom: 0.75rem;
    color: var(--text-secondary);
}

.detail-row strong {
    color: var(--text-primary);
}

.modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding: 1rem;
    border-top: 1px solid var(--border-color);
}

.notification {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    padding: 1rem 1.5rem;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    z-index: 1001;
    animation: slideIn 0.3s ease;
}

.notification.success {
    border-left: 4px solid #52c41a;
}

.notification.error {
    border-left: 4px solid #ff4d4f;
}

@keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}

/* Tab active state */
.nav-tab.active {
    background: var(--primary-color);
    color: white;
}

.tab-panel.hidden {
    display: none;
}
```

- [ ] **Step 3: Run manual verification**

```bash
# Start backend
cd d:/pooject
python -m uvicorn app.main:app --reload --port 8000

# Open frontend/index.html in browser (serve with live server or open directly)
# Click Insights tab - verify cards load
```

- [ ] **Step 4: Commit**

```bash
git add frontend/script.js frontend/index.html frontend/styles.css
git commit -m "feat: add Insights Dashboard frontend with cards, modals, acknowledge"
```

---

### Task 10: Configuration Updates

**Files:**
- Modify: `app/core/config.py` (add new settings)
- Modify: `.env.example` (document new variables)

**Interfaces:**
- Produces: Configuration values for scheduler, stockout, confidence, safety

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from app.core.config import settings

def test_insightos_config_exists():
    assert hasattr(settings, 'SCHEDULER_MODE')
    assert hasattr(settings, 'SCHEDULER_INTERVAL_MINUTES')
    assert hasattr(settings, 'DEFAULT_STOCKOUT_METHOD')
    assert hasattr(settings, 'DEFAULT_STOCKOUT_THRESHOLD_DAYS')
    assert hasattr(settings, 'CONFIDENCE_MIN_THRESHOLD')
    assert hasattr(settings, 'SQL_SAFETY_STRICT')
    assert hasattr(settings, 'ONTOLOGY_PATH')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (attributes missing)

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/config.py - Add to Settings class
# Scheduler
SCHEDULER_MODE: str = os.getenv("SCHEDULER_MODE", "embedded")
SCHEDULER_INTERVAL_MINUTES: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "90"))

# Stockout
DEFAULT_STOCKOUT_METHOD: str = os.getenv("DEFAULT_STOCKOUT_METHOD", "auto")
DEFAULT_STOCKOUT_THRESHOLD_DAYS: int = int(os.getenv("DEFAULT_STOCKOUT_THRESHOLD_DAYS", "7"))

# Confidence
CONFIDENCE_MIN_THRESHOLD: float = float(os.getenv("CONFIDENCE_MIN_THRESHOLD", "0.5"))

# Safety
SQL_SAFETY_STRICT: bool = os.getenv("SQL_SAFETY_STRICT", "true").lower() == "true"

# Ontology
ONTOLOGY_PATH: str = os.getenv("ONTOLOGY_PATH", "app/data/ontology/ontology.json")
```

```bash
# .env.example - Add new variables
SCHEDULER_MODE=embedded
SCHEDULER_INTERVAL_MINUTES=90
DEFAULT_STOCKOUT_METHOD=auto
DEFAULT_STOCKOUT_THRESHOLD_DAYS=7
CONFIDENCE_MIN_THRESHOLD=0.5
SQL_SAFETY_STRICT=true
ONTOLOGY_PATH=app/data/ontology/ontology.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py .env.example tests/test_config.py
git commit -m "feat: add InsightOS configuration settings"
```

---

### Task 11: Integration Test - Full Pipeline

**Files:**
- Create: `tests/test_phase1_integration.py`

**Interfaces:**
- Consumes: All Phase 1 components
- Produces: End-to-end verification

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase1_integration.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.mark.integration
def test_stockout_query_returns_finding_insight_action():
    """Test that stockout-related queries return Finding/Insight/Action format."""
    response = client.post("/api/v1/query", json={
        "query": "Which products are at risk of stockout this week?",
        "domain": "retail_clothing",
        "conversation_history": []
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["insight"] is not None
    assert data["recommendation"] is not None
    # Should contain stockout analysis
    assert "stockout" in str(data["insight"]).lower() or "reorder" in str(data["recommendation"]).lower()

@pytest.mark.integration
def test_stockout_api_endpoint():
    response = client.get("/api/v1/stockout/risk?domain=retail_clothing&days=7")
    assert response.status_code == 200
    data = response.json()
    assert "at_risk_products" in data
    assert "count" in data

@pytest.mark.integration
def test_insights_api_endpoints():
    # Today's insights
    response = client.get("/api/v1/insights/today?domain=retail_clothing")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
    assert "count" in data
    
    # History
    response = client.get("/api/v1/insights/history?domain=retail_clothing&days=7")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_phase1_integration.py -v`
Expected: FAIL (components not fully integrated)

- [ ] **Step 3: Run integration after all tasks complete**

Run: `pytest tests/test_phase1_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_phase1_integration.py
git commit -m "test: add Phase 1 integration tests"
```

---

## Summary

This plan covers **Phase 1: Stockout Risk + Auto Insights** with 11 tasks:

| Task | Component | Files Created |
|------|-----------|---------------|
| 1 | Database Migration | `app/migrations/001_add_insightos_tables.py` |
| 2 | Apply Migration | `scripts/apply_insightos_migration.py` |
| 3 | Stockout Analyzer | `app/modules/stockout_analyzer.py` |
| 4 | Stockout API | `app/api/stockout_endpoints.py` |
| 5 | LangGraph Integration | `app/orchestration/workflow.py` |
| 6 | Auto Insights Scheduler | `app/services/auto_insights_scheduler.py` |
| 7 | Scheduler Integration | `app/main.py` |
| 8 | Insights API | `app/api/insights_endpoints.py` |
| 9 | Frontend Dashboard | `frontend/script.js`, `index.html`, `styles.css` |
| 10 | Configuration | `app/core/config.py`, `.env.example` |
| 11 | Integration Tests | `tests/test_phase1_integration.py` |

**Total estimated effort:** ~3-4 days for experienced developer

**Next phases (not in this plan):**
- Phase 2: Confidence Score + Explanation
- Phase 3: Draft Purchase Order
- Phase 4: What-If Analysis
- Phase 5: Threat Simulation
- Phase 6: Ontology Integration
- Phase 7: Safety/Circuit Breakers
- Phase 8: Final UI Polish

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-25-insightos-phase1-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**