#!/usr/bin/env python3
"""
Tally Auto-Exporter Daemon for InsightOS.

This standalone utility runs in the background (on the Tally machine or server).
It continuously:
1. Queries Tally ERP 9 / TallyPrime XML Server (Port 9000).
2. Extracts live Stock Items & Sales Vouchers.
3. Automatically writes normalized Excel spreadsheets into the live_data/ directory:
   - live_data/inventory.xlsx
   - live_data/sales.xlsx
   - live_data/products.xlsx
4. Notifies InsightOS to immediately refresh Auto Insights and alerts.

Usage:
  python scripts/tally_auto_exporter.py --interval 300
  python scripts/tally_auto_exporter.py --once
  python scripts/tally_auto_exporter.py --host 192.168.1.100 --port 9000 --company "Acme Apparels"
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.tally_sync import (
    ping_tally_server,
    auto_sync_tally,
    fetch_tally_xml_via_http,
    parse_tally_xml,
    export_tally_to_excel_files,
    build_tally_stock_request_xml,
    build_tally_sales_request_xml
)
from app.services.excel_sync import sync_excel_to_db


def run_daemon(
    host: str = "localhost",
    port: int = 9000,
    company: str = None,
    interval_seconds: int = 300,
    live_data_dir: str = "live_data",
    db_path: str = "retail_clothing.db",
    run_once: bool = False
):
    print("=" * 70)
    print("  InsightOS - Automated Tally Data Synchronization Daemon")
    print("=" * 70)
    print(f"  Target Tally Server : http://{host}:{port}")
    if company:
        print(f"  Target Company      : {company}")
    print(f"  Export Directory    : {os.path.abspath(live_data_dir)}")
    print(f"  Database Path       : {os.path.abspath(db_path)}")
    print(f"  Polling Interval    : {interval_seconds} seconds")
    print(f"  Mode                : {'Single-Run' if run_once else 'Continuous Daemon'}")
    print("=" * 70)

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Checking Tally server connectivity...")

        ping = ping_tally_server(host=host, port=port)
        if not ping.get("online"):
            print(f"  [WARN] Tally server unreachable at http://{host}:{port}")
            print(f"  [INFO] Error: {ping.get('error')}")
            print("  [TIP]  Ensure Tally is running and ODBC/XML Server is enabled on Port 9000.")
        else:
            print(f"  [OK]   Tally server online! (Latency: {ping.get('latency_ms')}ms)")
            print("  [SYNC] Pulling Stock & Sales vouchers from Tally...")

            result = auto_sync_tally(
                host=host,
                port=port,
                company=company,
                live_data_dir=live_data_dir,
                db_path=db_path
            )

            if result.get("status") == "SUCCESS":
                stock_count = result.get("stock_items_fetched", 0)
                sales_count = result.get("sales_vouchers_fetched", 0)
                print(f"  [SUCCESS] Extracted {stock_count} stock items and {sales_count} sales vouchers.")
                print(f"  [FILES]   Updated Excel spreadsheets in '{live_data_dir}/'")
                print(f"  [DB]      Synced with '{db_path}' and refreshed Auto Insights!")
            else:
                print(f"  [ERROR] Sync failed: {result.get('error') or result.get('message')}")

        if run_once:
            print("\n[DONE] Single-run execution complete.")
            break

        print(f"\nSleeping for {interval_seconds} seconds before next sync...")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="InsightOS Automated Tally Data Exporter")
    parser.add_argument("--host", type=str, default="localhost", help="Tally server hostname/IP (default: localhost)")
    parser.add_argument("--port", type=int, default=9000, help="Tally XML port (default: 9000)")
    parser.add_argument("--company", type=str, default=None, help="Tally company name (optional)")
    parser.add_argument("--interval", type=int, default=300, help="Sync interval in seconds (default: 300 / 5 mins)")
    parser.add_argument("--live-data-dir", type=str, default="live_data", help="Output directory for Excel files (default: live_data)")
    parser.add_argument("--db", type=str, default="retail_clothing.db", help="Target SQLite database (default: retail_clothing.db)")
    parser.add_argument("--once", action="store_true", help="Execute sync once and exit")

    args = parser.parse_args()

    run_daemon(
        host=args.host,
        port=args.port,
        company=args.company,
        interval_seconds=args.interval,
        live_data_dir=args.live_data_dir,
        db_path=args.db,
        run_once=args.once
    )


if __name__ == "__main__":
    main()
