"""
Test Suite for Advanced Automated Data Synchronization:
1. Tally Auto Sync (Folder Watcher & HTTP Pull)
2. Shared Network Folder Sync
3. Google Sheets Live Sync
4. Unified Multi-Source Status Endpoint (/sync/status/all)
"""

import pytest
import sqlite3
import os
import tempfile
import pandas as pd
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.excel_sync import init_sync_schema
from app.services.tally_auto_sync import sync_tally_export_folder, run_tally_auto_sync
from app.services.network_folder_sync import sync_network_folder
from app.services.google_sheets_sync import sync_google_sheets, fetch_sheet_via_http_csv

client = TestClient(app)


def setup_test_database(db_path: str):
    """Initializes SQLite database with master schema for testing."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE products (
            sku TEXT PRIMARY KEY,
            style_name TEXT NOT NULL,
            category TEXT,
            unit_cost REAL,
            retail_price REAL,
            supplier_id TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE inventory (
            sku TEXT PRIMARY KEY,
            stock_count INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL DEFAULT 10,
            location TEXT,
            last_restocked_at TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE sales_events (
            event_id TEXT PRIMARY KEY,
            sku TEXT NOT NULL,
            units_sold INTEGER NOT NULL,
            sale_price REAL,
            sale_date DATE,
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

    init_sync_schema(conn)
    conn.commit()
    conn.close()


def test_tally_export_folder_watcher():
    """Test automatic ingestion of Tally export folder XML & Excel dumps."""
    with tempfile.TemporaryDirectory() as export_dir, tempfile.TemporaryDirectory() as live_dir:
        db_path = os.path.join(export_dir, "test.db")
        setup_test_database(db_path)

        # 1. Create a mock Tally XML export file in export folder
        xml_content = """<?xml version="1.0"?>
        <ENVELOPE>
            <BODY>
                <DATA>
                    <TALLYMESSAGE>
                        <STOCKITEM NAME="Tally Cotton Polo Shirt">
                            <CLOSINGBALANCE>60 Pcs</CLOSINGBALANCE>
                            <PARENT>Casuals</PARENT>
                            <CLOSINGRATE>450</CLOSINGRATE>
                        </STOCKITEM>
                    </TALLYMESSAGE>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        with open(os.path.join(export_dir, "Tally_Stock.xml"), "w", encoding="utf-8") as f:
            f.write(xml_content)

        # Run folder sync
        res = sync_tally_export_folder(
            export_folder=export_dir,
            db_path=db_path,
            live_data_dir=live_dir,
            force=True
        )

        assert res["status"] == "SUCCESS"
        assert len(res["files_processed"]) == 1
        assert "Tally_Stock.xml" in res["files_processed"]

        # Verify DB insertion
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        p_row = cursor.execute("SELECT style_name FROM products WHERE style_name LIKE '%Cotton Polo%'").fetchone()
        i_row = cursor.execute("SELECT stock_count FROM inventory WHERE sku LIKE '%TALLY%'").fetchone()
        conn.close()

        assert p_row is not None
        assert i_row[0] == 60


def test_network_folder_sync():
    """Test reading Excel spreadsheets from a shared network folder."""
    with tempfile.TemporaryDirectory() as network_share_dir:
        db_path = os.path.join(network_share_dir, "test.db")
        setup_test_database(db_path)

        # Create Excel file in network share
        inv_df = pd.DataFrame([
            {"sku": "NET-001", "stock_count": 88, "reorder_point": 12, "location": "Warehouse-North"},
            {"sku": "NET-002", "stock_count": 5, "reorder_point": 15, "location": "Warehouse-South"}
        ])
        inv_df.to_excel(os.path.join(network_share_dir, "inventory_network.xlsx"), sheet_name="Inventory", index=False)

        prod_df = pd.DataFrame([
            {"sku": "NET-001", "style_name": "Denim Jacket", "category": "Outerwear", "unit_cost": 40.0, "retail_price": 95.0},
            {"sku": "NET-002", "style_name": "Silk Scarf", "category": "Accessories", "unit_cost": 15.0, "retail_price": 35.0}
        ])
        prod_df.to_excel(os.path.join(network_share_dir, "products_network.xlsx"), sheet_name="Products", index=False)

        # Sync from network path
        res = sync_network_folder(
            network_folder_path=network_share_dir,
            db_path=db_path,
            force=True
        )

        assert res["status"] == "SUCCESS"
        assert len(res["files_processed"]) == 2

        # Verify in DB
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        i_count = cursor.execute("SELECT COUNT(*) FROM inventory WHERE sku LIKE 'NET-%'").fetchone()[0]
        p_count = cursor.execute("SELECT COUNT(*) FROM products WHERE sku LIKE 'NET-%'").fetchone()[0]
        conn.close()

        assert i_count == 2
        assert p_count == 2


def test_network_folder_offline_handling():
    """Test that unreachable network path fails gracefully without crashing."""
    res = sync_network_folder(
        network_folder_path=r"\\nonexistent_server\share\data",
        db_path="retail_clothing.db"
    )
    assert res["status"] == "OFFLINE"
    assert "unreachable" in res["message"].lower()


@patch("app.services.google_sheets_sync.fetch_sheet_via_http_csv")
def test_google_sheets_sync(mock_fetch_csv):
    """Test Google Sheets synchronization with mocked sheet CSV downloads."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        setup_test_database(db_path)

        def mock_sheet_side_effect(sheet_id, sheet_name, timeout=10.0):
            if sheet_name == "Inventory":
                return pd.DataFrame([
                    {"sku": "GS-101", "stock_count": 22, "reorder_point": 10, "location": "E-Comm FC"}
                ])
            elif sheet_name == "Products":
                return pd.DataFrame([
                    {"sku": "GS-101", "style_name": "Merino Wool Sweater", "category": "Knitwear", "unit_cost": 30.0, "retail_price": 75.0}
                ])
            elif sheet_name == "Sales":
                return pd.DataFrame([
                    {"sku": "GS-101", "units_sold": 4, "sale_date": "2026-09-22", "channel": "Google Store"}
                ])
            return pd.DataFrame()

        mock_fetch_csv.side_effect = mock_sheet_side_effect

        res = sync_google_sheets(
            sheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            credentials_file="nonexistent_creds.json",
            db_path=db_path,
            sheet_names=["Inventory", "Products", "Sales"]
        )

        assert res["status"] == "SUCCESS"
        assert res["rows_synced"] >= 3
        assert "Inventory" in res["sheets_processed"]
        assert "Products" in res["sheets_processed"]

        # Check DB
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        p_row = cursor.execute("SELECT style_name FROM products WHERE sku = 'GS-101'").fetchone()
        i_row = cursor.execute("SELECT stock_count FROM inventory WHERE sku = 'GS-101'").fetchone()
        s_row = cursor.execute("SELECT units_sold FROM sales_events WHERE sku = 'GS-101'").fetchone()
        conn.close()

        assert p_row[0] == "Merino Wool Sweater"
        assert i_row[0] == 22
        assert s_row[0] == 4


def test_unified_sync_status_api():
    """Test GET /api/v1/sync/status/all endpoint."""
    resp = client.get("/api/v1/sync/status/all?db_path=retail_clothing.db")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert "configuration" in data
    assert "tally" in data["configuration"]
    assert "google_sheets" in data["configuration"]
    assert "network_folder" in data["configuration"]
    assert "sources" in data
    assert "recent_logs" in data


def test_trigger_sync_api_endpoints():
    """Test trigger endpoints for all sources."""
    # 1. Tally Auto endpoint
    tally_resp = client.post("/api/v1/sync/tally/auto?port=59999")
    assert tally_resp.status_code == 200

    # 2. Network folder endpoint (validation on missing path)
    nf_resp = client.post("/api/v1/sync/network-folder")
    assert nf_resp.status_code in [200, 400]

    # 3. Google sheets endpoint (validation on missing ID)
    gs_resp = client.post("/api/v1/sync/google-sheets")
    assert gs_resp.status_code in [200, 400]
