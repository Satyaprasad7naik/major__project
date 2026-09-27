"""
Test suite for Live Data Sync (Excel + Automated Tally -> InsightOS).
"""

import pytest
import sqlite3
import os
import tempfile
import pandas as pd
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.excel_sync import sync_excel_to_db, get_sync_status
from app.services.tally_sync import (
    sync_tally_xml_to_db,
    parse_tally_xml,
    build_tally_stock_request_xml,
    build_tally_sales_request_xml,
    ping_tally_server,
    export_tally_to_excel_files,
    auto_sync_tally
)

client = TestClient(app)


def setup_sync_db(db_path: str):
    """Create test SQLite database tables for live sync tests."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE products (
            product_id TEXT,
            name TEXT,
            sku TEXT PRIMARY KEY,
            style_name TEXT,
            category TEXT,
            unit_cost REAL,
            retail_price REAL,
            supplier_id TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE inventory (
            product_id TEXT,
            sku TEXT PRIMARY KEY,
            current_stock INTEGER,
            stock_count INTEGER,
            reorder_point INTEGER NOT NULL,
            location TEXT,
            warehouse_id TEXT,
            last_restocked_at TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE sales_events (
            event_id TEXT PRIMARY KEY,
            sku TEXT,
            product_id TEXT,
            units_sold INTEGER,
            quantity INTEGER,
            sale_price REAL,
            sale_date DATE,
            transaction_date DATE,
            store_id TEXT,
            channel TEXT
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
            product_id TEXT,
            product_name TEXT,
            sku TEXT,
            supplier_id TEXT,
            payload_json TEXT,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()


def test_excel_data_sync():
    """Test syncing products, inventory, and sales from Excel files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_sync.db")
        setup_sync_db(db_path)

        # Create sample Excel files
        prod_df = pd.DataFrame([
            {"sku": "SKU-9001", "style_name": "Organic Cotton Tee", "category": "Apparel", "unit_cost": 20.0, "retail_price": 50.0},
            {"sku": "SKU-9002", "style_name": "Linen Trousers", "category": "Apparel", "unit_cost": 35.0, "retail_price": 85.0}
        ])
        prod_df.to_excel(os.path.join(tmp_dir, "products.xlsx"), index=False, sheet_name="Products")

        inv_df = pd.DataFrame([
            {"sku": "SKU-9001", "stock_count": 4, "reorder_point": 15, "location": "Main Warehouse"},
            {"sku": "SKU-9002", "stock_count": 80, "reorder_point": 20, "location": "Main Warehouse"}
        ])
        inv_df.to_excel(os.path.join(tmp_dir, "inventory.xlsx"), index=False, sheet_name="Inventory")

        sales_df = pd.DataFrame([
            {"sku": "SKU-9001", "units_sold": 5, "sale_date": "2026-09-01", "channel": "Online"},
            {"sku": "SKU-9002", "units_sold": 12, "sale_date": "2026-09-01", "channel": "Retail"}
        ])
        sales_df.to_excel(os.path.join(tmp_dir, "sales.xlsx"), index=False, sheet_name="Sales")

        # Run sync
        res = sync_excel_to_db(db_path=db_path, live_data_dir=tmp_dir, force=True)

        assert res["status"] == "SUCCESS"
        assert len(res["files_processed"]) == 3
        assert res["rows_synced"] >= 6

        # Verify DB records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        p_count = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        i_count = cursor.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        s_count = cursor.execute("SELECT COUNT(*) FROM sales_events").fetchone()[0]
        conn.close()

        assert p_count == 2
        assert i_count == 2
        assert s_count == 2


def test_tally_envelopes_and_ping():
    """Test Tally XML envelope building and ping connectivity."""
    stock_req = build_tally_stock_request_xml(company="Test Apparels Ltd")
    assert "Stock Summary" in stock_req
    assert "Test Apparels Ltd" in stock_req

    sales_req = build_tally_sales_request_xml(company="Test Apparels Ltd", from_date="20260901", to_date="20260930")
    assert "Voucher Register" in sales_req
    assert "20260901" in sales_req

    # Ping non-existent local port to verify offline handling
    ping_res = ping_tally_server(host="127.0.0.1", port=59999, timeout=0.5)
    assert ping_res["online"] is False
    assert "offline" in ping_res["message"].lower() or "unreachable" in ping_res["message"].lower()


def test_tally_to_excel_transformation():
    """Test converting parsed Tally XML data into normalized Excel spreadsheets."""
    xml_sample = """<?xml version="1.0"?>
    <ENVELOPE>
        <BODY>
            <DATA>
                <TALLYMESSAGE>
                    <STOCKITEM NAME="Tally Premium Wool Blazer">
                        <CLOSINGBALANCE>35 Pcs</CLOSINGBALANCE>
                        <PARENT>Formalwear</PARENT>
                        <CLOSINGRATE>1200</CLOSINGRATE>
                    </STOCKITEM>
                </TALLYMESSAGE>
                <TALLYMESSAGE>
                    <VOUCHER VOUCHERTYPENAME="Sales">
                        <DATE>20260921</DATE>
                        <ALLINVENTORYENTRIES>
                            <STOCKITEMNAME>Tally Premium Wool Blazer</STOCKITEMNAME>
                            <ACTUALQTY>4 Pcs</ACTUALQTY>
                        </ALLINVENTORYENTRIES>
                    </VOUCHER>
                </TALLYMESSAGE>
            </DATA>
        </BODY>
    </ENVELOPE>"""

    parsed = parse_tally_xml(xml_sample)
    assert len(parsed["stock_items"]) == 1
    assert parsed["stock_items"][0]["stock_count"] == 35
    assert len(parsed["sales_vouchers"]) == 1
    assert parsed["sales_vouchers"][0]["units_sold"] == 4

    with tempfile.TemporaryDirectory() as tmp_dir:
        excel_res = export_tally_to_excel_files(parsed, live_data_dir=tmp_dir)
        assert excel_res["status"] == "SUCCESS"
        assert "inventory.xlsx" in excel_res["files_written"]
        assert "sales.xlsx" in excel_res["files_written"]
        assert "products.xlsx" in excel_res["files_written"]

        # Confirm Excel files exist and have data
        df_inv = pd.read_excel(os.path.join(tmp_dir, "inventory.xlsx"), sheet_name="Inventory")
        assert len(df_inv) == 1
        assert df_inv.iloc[0]["Stock_Count"] == 35

        df_sales = pd.read_excel(os.path.join(tmp_dir, "sales.xlsx"), sheet_name="Sales")
        assert len(df_sales) == 1
        assert df_sales.iloc[0]["Units_Sold"] == 4


def test_tally_api_endpoints():
    """Test /api/v1/sync/tally/ping and /api/v1/sync/tally/export-excel."""
    # 1. Ping
    ping_resp = client.get("/api/v1/sync/tally/ping?port=59999")
    assert ping_resp.status_code == 200
    assert "online" in ping_resp.json()

    # 2. Export Excel endpoint
    xml_sample = """<ENVELOPE><BODY><DATA>
        <STOCKITEM NAME="Tally Chinos"><CLOSINGBALANCE>18 Pcs</CLOSINGBALANCE></STOCKITEM>
    </DATA></BODY></ENVELOPE>"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        resp = client.post(
            f"/api/v1/sync/tally/export-excel?live_data_dir={tmp_dir}",
            content=xml_sample,
            headers={"Content-Type": "application/xml"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUCCESS"
        assert os.path.exists(os.path.join(tmp_dir, "inventory.xlsx"))
