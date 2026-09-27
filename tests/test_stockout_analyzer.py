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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])