"""
Manual Testing Script for Tally Integration in InsightOS
=========================================================
Tests and demonstrates all 3 ways to test Tally data synchronization:
1. Live Tally HTTP Ping (checks port 9000).
2. Mock Tally XML Ingestion (tests parsing & database update without Tally software).
3. Folder Export & Excel generation in live_data/.
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.services.tally_sync import (
    ping_tally_server,
    parse_tally_xml,
    sync_tally_xml_to_db,
    export_tally_to_excel_files,
)
from app.services.auto_insights import generate_insights


SAMPLE_TALLY_XML = """<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDATA>
        <!-- Stock Items Master -->
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <STOCKITEM NAME="Slim Fit Oxford Shirt" ACTION="Create">
            <NAME>Slim Fit Oxford Shirt</NAME>
            <PARENT>Tops</PARENT>
            <BASEUNITS>Pcs</BASEUNITS>
            <OPENINGBALANCE>45 Pcs</OPENINGBALANCE>
            <CLOSINGBALANCE>12 Pcs</CLOSINGBALANCE>
            <CLOSINGRATE>45.00</CLOSINGRATE>
            <CLOSINGVALUE>540.00</CLOSINGVALUE>
            <REORDERLEVEL>20</REORDERLEVEL>
            <MINORDERQTY>10</MINORDERQTY>
          </STOCKITEM>
        </TALLYMESSAGE>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <STOCKITEM NAME="Classic Denim Jeans" ACTION="Create">
            <NAME>Classic Denim Jeans</NAME>
            <PARENT>Bottoms</PARENT>
            <BASEUNITS>Pcs</BASEUNITS>
            <OPENINGBALANCE>30 Pcs</OPENINGBALANCE>
            <CLOSINGBALANCE>2 Pcs</CLOSINGBALANCE>
            <CLOSINGRATE>65.00</CLOSINGRATE>
            <CLOSINGVALUE>130.00</CLOSINGVALUE>
            <REORDERLEVEL>15</REORDERLEVEL>
            <MINORDERQTY>10</MINORDERQTY>
          </STOCKITEM>
        </TALLYMESSAGE>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <STOCKITEM NAME="Leather Chelsea Boots" ACTION="Create">
            <NAME>Leather Chelsea Boots</NAME>
            <PARENT>Footwear</PARENT>
            <BASEUNITS>Pairs</BASEUNITS>
            <OPENINGBALANCE>20 Pairs</OPENINGBALANCE>
            <CLOSINGBALANCE>0 Pairs</CLOSINGBALANCE>
            <CLOSINGRATE>110.00</CLOSINGRATE>
            <CLOSINGVALUE>0.00</CLOSINGVALUE>
            <REORDERLEVEL>10</REORDERLEVEL>
            <MINORDERQTY>15</MINORDERQTY>
          </STOCKITEM>
        </TALLYMESSAGE>

        <!-- Sales Voucher (Transaction) -->
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER VCHTYPE="Sales" ACTION="Create">
            <DATE>20260923</DATE>
            <VOUCHERNUMBER>INV-TALLY-2026-001</VOUCHERNUMBER>
            <PARTYLEDGERNAME>Retail Walk-In Customer</PARTYLEDGERNAME>
            <ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>Slim Fit Oxford Shirt</STOCKITEMNAME>
              <ACTUALQTY>3 Pcs</ACTUALQTY>
              <BILLEDQTY>3 Pcs</BILLEDQTY>
              <RATE>75.00</RATE>
              <AMOUNT>225.00</AMOUNT>
            </ALLINVENTORYENTRIES.LIST>
            <ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>Classic Denim Jeans</STOCKITEMNAME>
              <ACTUALQTY>1 Pcs</ACTUALQTY>
              <BILLEDQTY>1 Pcs</BILLEDQTY>
              <RATE>95.00</RATE>
              <AMOUNT>95.00</AMOUNT>
            </ALLINVENTORYENTRIES.LIST>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>
"""


def test_tally_manual():
    print("=" * 65)
    print(" InsightOS - Tally Integration Manual Testing Suite")
    print("=" * 65)

    # Test 1: Check Live Tally Connection
    print("\n[TEST 1] Testing live connection to Tally ERP 9 / TallyPrime (Port 9000)...")
    ping = ping_tally_server(host="localhost", port=9000)
    if ping.get("online"):
        print("  [SUCCESS] Tally server is online and responding!")
        print(f"  - Host/Port: {ping.get('host')}:{ping.get('port')}")
        print(f"  - Latency:   {ping.get('latency_ms')} ms")
    else:
        print("  [INFO] Real Tally server is not running on localhost:9000.")
        print(f"  - Message: {ping.get('message')}")
        print("  - Note: You can still test Tally sync using Mock XML below!")

    # Test 2: Parse Sample Tally XML
    print("\n[TEST 2] Parsing Sample Tally XML payload...")
    parsed = parse_tally_xml(SAMPLE_TALLY_XML)
    stock_items = parsed.get("stock_items", [])
    sales_vouchers = parsed.get("sales_vouchers", [])
    print(f"  [SUCCESS] Extracted {len(stock_items)} Stock Items and {len(sales_vouchers)} Sales Vouchers.")
    for item in stock_items:
        print(f"    * Product: {item.get('style_name', item.get('name'))} | Stock: {item.get('stock_count')} | Reorder Point: {item.get('reorder_point')}")

    # Test 3: Ingest Tally XML directly into SQLite database
    print("\n[TEST 3] Ingesting parsed Tally data into retail_clothing.db...")
    res_db = sync_tally_xml_to_db(SAMPLE_TALLY_XML, db_path="retail_clothing.db")
    print("  [SUCCESS] Database updated with Tally payload:")
    print(f"  - Stock Items Synced: {res_db.get('stock_items_synced')}")
    print(f"  - Vouchers Synced:    {res_db.get('vouchers_synced')}")
    print(f"  - Total Rows Synced:  {res_db.get('rows_synced')}")

    # Test 4: Export Tally data to normalized Excel files
    print("\n[TEST 4] Exporting Tally data to live_data/ Excel spreadsheets...")
    os.makedirs("live_data", exist_ok=True)
    res_excel = export_tally_to_excel_files(parsed, live_data_dir="live_data")
    print(f"  [SUCCESS] Created Excel files: {res_excel.get('files_written')}")

    # Test 5: Trigger Auto Insights on the new Tally data
    print("\n[TEST 5] Generating Auto Insights on newly synchronized Tally data...")
    insights = generate_insights("retail_clothing.db")
    print(f"  [SUCCESS] Generated {len(insights)} business insights from updated data.")
    for i, ins in enumerate(insights[:3], 1):
        headline = ins.get("headline") or ins.get("title") or ins.get("finding") or "Stock Alert"
        print(f"    [{i}] {headline}")
        print(f"        Action: {ins.get('recommended_action') or ins.get('action')}")

    print("\n" + "=" * 65)
    print(" All manual Tally tests completed successfully!")
    print("=" * 65)


if __name__ == "__main__":
    test_tally_manual()
