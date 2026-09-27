"""
Test suite for Auto-generated Insights (Proactive Insights).
"""

import pytest
import sqlite3
import os
import tempfile
import asyncio
from fastapi.testclient import TestClient
from app.main import app
from app.services.auto_insights import generate_insights, get_db_connection
from app.services.email_notifier import send_email_insight_alert, format_insight_email_html
from app.services.slack_notifier import notify_slack

client = TestClient(app)


def setup_test_db(db_path: str):
    """Setup mock sqlite database with products, inventory, sales, and auto_insights schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Schema
    cursor.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            sku TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE inventory (
            product_id INTEGER PRIMARY KEY,
            current_stock INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            days_of_cover REAL
        );
    """)

    cursor.execute("""
        CREATE TABLE sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            sale_date DATE NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE auto_insights (
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

    # Populate Test Data
    # Product 1: Low days of cover (< 3)
    # Product 2: Sales drop (recent qty = 5, prev qty = 50 -> drop -90%)
    # Product 3: High risk (stock = 0)
    cursor.executemany("""
        INSERT INTO products (product_id, name, category, sku) VALUES (?, ?, ?, ?);
    """, [
        (101, "Silk Dress", "Apparel", "SKU-101"),
        (102, "Denim Jacket", "Apparel", "SKU-102"),
        (103, "Leather Boots", "Footwear", "SKU-103")
    ])

    cursor.executemany("""
        INSERT INTO inventory (product_id, current_stock, reorder_point, days_of_cover) VALUES (?, ?, ?, ?);
    """, [
        (101, 2, 10, 1.0),
        (102, 50, 15, 10.0),
        (103, 0, 5, 0.0)
    ])

    # Sales history over 14 days
    today_str = "2026-09-02"
    sales_data = []
    # Product 101 high sales (avg 5/day)
    for d in range(14):
        date_val = f"2026-08-{19+d:02d}"
        sales_data.append((101, 5, date_val))

    # Product 102: Prev week (days 0-6) = 10/day (total 70), Recent week (days 7-13) = 1/day (total 7) -> drop
    for d in range(7):
        date_val = f"2026-08-{19+d:02d}"
        sales_data.append((102, 10, date_val))
    for d in range(7, 14):
        date_val = f"2026-08-{19+d:02d}"
        sales_data.append((102, 1, date_val))

    cursor.executemany("""
        INSERT INTO sales (product_id, quantity, sale_date) VALUES (?, ?, ?);
    """, sales_data)

    conn.commit()
    conn.close()


def test_auto_insights_generation():
    """Test generating proactive insights from test DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        setup_test_db(db_path)
        insights = generate_insights(db_path)

        assert isinstance(insights, list)
        assert len(insights) >= 2

        # Check types generated
        types = [i["insight_type"] for i in insights]
        assert "stockout" in types or "high_risk" in types

        # Check DB persistence
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        stored = cursor.execute("SELECT COUNT(*) FROM auto_insights").fetchone()[0]
        conn.close()
        assert stored >= 2
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_insights_today_api_endpoint():
    """Test GET /api/v1/insights/today endpoint response structure."""
    response = client.get("/api/v1/insights/today?domain=retail_clothing")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
    assert "summary_headline" in data
    assert "urgent_count" in data
    assert isinstance(data["insights"], list)
    assert isinstance(data["summary_headline"], str)


def test_mark_insight_as_read_api():
    """Test PATCH /api/v1/insights/{insight_id}/read endpoint."""
    response = client.patch("/api/v1/insights/INS-TEST-001/read")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("is_read") is True


def test_email_formatter():
    """Test HTML formatting for proactive email alerts."""
    test_insights = [{
        "title": "Silk Dress running low",
        "description": "Only 1.0 days of stock left.",
        "severity": "high",
        "product_name": "Silk Dress"
    }]
    html = format_insight_email_html(test_insights, "1 products need urgent attention today")
    assert "Silk Dress running low" in html
    assert "1 products need urgent attention today" in html


@pytest.mark.asyncio
async def test_email_alert_fallback():
    """Test email alert dispatcher falls back gracefully when SMTP omitted."""
    test_insights = [{
        "title": "Critical Stockout: Leather Boots",
        "description": "Stock count is 0 units.",
        "severity": "critical",
        "product_name": "Leather Boots"
    }]
    result = await send_email_insight_alert(test_insights, "1 products need urgent attention today")
    # Returns False when no SMTP credentials configured, but executes cleanly without throwing
    assert result is False
