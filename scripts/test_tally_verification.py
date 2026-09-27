"""Quick verification script for Tally Auto Sync capabilities."""
import os
import tempfile
import pandas as pd
from app.services.tally_sync import (
    build_tally_stock_request_xml,
    build_tally_sales_request_xml,
    ping_tally_server,
    parse_tally_xml,
    export_tally_to_excel_files,
    auto_sync_tally
)
from app.services.excel_sync import sync_excel_to_db

def run_tests():
    print("1. Testing XML Envelope Generation...")
    stock_req = build_tally_stock_request_xml("Apex Fashions")
    assert "Stock Summary" in stock_req
    assert "Apex Fashions" in stock_req
    print("   [OK] Stock XML envelope generated successfully.")

    sales_req = build_tally_sales_request_xml("Apex Fashions", "20260901", "20260922")
    assert "Voucher Register" in sales_req
    assert "20260901" in sales_req
    print("   [OK] Sales XML envelope generated successfully.")

    print("\n2. Testing Tally XML Parser...")
    xml_sample = """<?xml version="1.0"?>
    <ENVELOPE>
        <BODY>
            <DATA>
                <TALLYMESSAGE>
                    <STOCKITEM NAME="Tally Premium Wool Blazer">
                        <CLOSINGBALANCE>45 Pcs</CLOSINGBALANCE>
                        <PARENT>Formalwear</PARENT>
                        <CLOSINGRATE>1500</CLOSINGRATE>
                    </STOCKITEM>
                </TALLYMESSAGE>
                <TALLYMESSAGE>
                    <VOUCHER VOUCHERTYPENAME="Sales">
                        <DATE>20260922</DATE>
                        <ALLINVENTORYENTRIES>
                            <STOCKITEMNAME>Tally Premium Wool Blazer</STOCKITEMNAME>
                            <ACTUALQTY>5 Pcs</ACTUALQTY>
                        </ALLINVENTORYENTRIES>
                    </VOUCHER>
                </TALLYMESSAGE>
            </DATA>
        </BODY>
    </ENVELOPE>"""
    parsed = parse_tally_xml(xml_sample)
    assert len(parsed["stock_items"]) == 1
    assert parsed["stock_items"][0]["stock_count"] == 45
    assert len(parsed["sales_vouchers"]) == 1
    assert parsed["sales_vouchers"][0]["units_sold"] == 5
    print(f"   [OK] Parsed {len(parsed['stock_items'])} stock item(s) and {len(parsed['sales_vouchers'])} voucher(s).")

    print("\n3. Testing Excel Transformation to live_data/ folder...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = export_tally_to_excel_files(parsed, live_data_dir=tmp_dir)
        assert res["status"] == "SUCCESS"
        assert "inventory.xlsx" in res["files_written"]
        assert "sales.xlsx" in res["files_written"]
        assert "products.xlsx" in res["files_written"]

        df_inv = pd.read_excel(os.path.join(tmp_dir, "inventory.xlsx"), sheet_name="Inventory")
        assert len(df_inv) == 1
        assert df_inv.iloc[0]["Stock_Count"] == 45
        print(f"   [OK] Excel files created: {res['files_written']}")
        print(f"   [OK] Verified inventory.xlsx contains 45 units for {df_inv.iloc[0]['SKU']}.")

    print("\n4. Testing Tally Ping Server...")
    ping = ping_tally_server(host="127.0.0.1", port=9000)
    print(f"   [OK] Ping completed (Online: {ping['online']}, Message: {ping['message']})")

    print("\n5. Testing Graceful Offline Auto-Sync...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        offline_res = auto_sync_tally(host="127.0.0.1", port=59999, live_data_dir=tmp_dir)
        assert offline_res["status"] == "OFFLINE"
        print(f"   [OK] Offline status handled gracefully without exception.")

    print("\n=======================================================")
    print("  ALL TALLY AUTOMATIC SYNC TESTS PASSED SUCCESSFULLY!  ")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
