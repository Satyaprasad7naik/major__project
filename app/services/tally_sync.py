"""
Tally Integration & Auto-Sync Service for InsightOS.
Provides automated HTTP fetching from Tally ERP 9 / TallyPrime (Port 9000),
XML parsing, automated Excel generation into live_data/ folder,
and seamless synchronization with SQLite database and Auto Insights.
"""

import os
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

from app.core.logger import logger
from app.services.auto_insights import generate_insights, get_db_connection
from app.services.excel_sync import init_sync_schema, sync_excel_to_db


# ─────────────────────────────────────────────────────────────────────────────
# Tally XML Request Envelopes
# ─────────────────────────────────────────────────────────────────────────────

def build_tally_stock_request_xml(company: Optional[str] = None) -> str:
    """
    Build standard Tally XML envelope to export Stock Item Master & Summary data.
    """
    company_tag = f"<STATICVARIABLES><SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY></STATICVARIABLES>" if company else ""
    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Stock Summary</REPORTNAME>
        {company_tag}
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>""".strip()


def build_tally_sales_request_xml(
    company: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> str:
    """
    Build standard Tally XML envelope to export Sales Vouchers.
    """
    company_tag = f"<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>" if company else ""
    sv_from = f"<SVFROMDATE>{from_date}</SVFROMDATE>" if from_date else ""
    sv_to = f"<SVTODATE>{to_date}</SVTODATE>" if to_date else ""
    static_vars = f"<STATICVARIABLES>{company_tag}{sv_from}{sv_to}</STATICVARIABLES>" if (company_tag or sv_from or sv_to) else ""

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Voucher Register</REPORTNAME>
        {static_vars}
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Tally Server Connectivity & HTTP Client
# ─────────────────────────────────────────────────────────────────────────────

def ping_tally_server(host: str = "localhost", port: int = 9000, timeout: float = 2.0) -> Dict[str, Any]:
    """
    Check connectivity to the Tally ERP 9 / TallyPrime XML Server.
    """
    url = f"http://{host}:{port}"
    start_time = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            data=b"<ENVELOPE><HEADER><TALLYREQUEST>GetLicenseInfo</TALLYREQUEST></HEADER><BODY></BODY></ENVELOPE>",
            headers={"Content-Type": "text/xml;charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "online": True,
                "url": url,
                "status_code": response.status,
                "latency_ms": latency_ms,
                "message": "Tally XML server is online and responding."
            }
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as err:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "online": False,
            "url": url,
            "latency_ms": latency_ms,
            "error": str(err),
            "message": f"Tally server is unreachable at {url}. Ensure Tally is open with ODBC/XML enabled on port {port}."
        }


def fetch_tally_xml_via_http(
    xml_request: str,
    host: str = "localhost",
    port: int = 9000,
    timeout: float = 10.0
) -> str:
    """
    Sends an XML query envelope to Tally's HTTP endpoint and returns the XML response.
    """
    url = f"http://{host}:{port}"
    data_bytes = xml_request.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Content-Type": "text/xml;charset=utf-8",
            "Content-Length": str(len(data_bytes))
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_content = resp.read().decode("utf-8", errors="replace")
            return response_content
    except Exception as exc:
        logger.error(f"HTTP communication with Tally at {url} failed: {exc}")
        raise ConnectionError(f"Could not connect to Tally at {url}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tally XML Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_tally_xml(xml_content: str) -> Dict[str, Any]:
    """
    Parses Tally XML export payload containing Stock Items (Master) or Vouchers (Transactions).
    Extracts stock item names, quantities, categories, unit prices, and sales records.
    """
    items = []
    vouchers = []

    try:
        root = ET.fromstring(xml_content)

        # 1. Search for STOCKITEM nodes (Master & Summary)
        for item_node in root.findall(".//STOCKITEM"):
            name = item_node.get("NAME") or (item_node.findtext("NAME") if item_node.find("NAME") is not None else "Unknown Item")
            closing_qty = item_node.findtext("CLOSINGBALANCE") or item_node.findtext("OPENINGBALANCE") or "0"
            parent_cat = item_node.findtext("PARENT") or "Tally Master"
            rate_str = item_node.findtext("CLOSINGRATE") or item_node.findtext("BASEUNITS") or "0"

            # Parse quantity (e.g. '50 Pcs' or '-10 Nos' -> 50)
            qty_num = 0
            try:
                digits = "".join(ch for ch in closing_qty if ch.isdigit() or ch == "-")
                qty_num = int(digits) if digits and digits != "-" else 0
            except ValueError:
                pass

            # Parse unit cost / rate
            unit_rate = 0.0
            try:
                rate_digits = "".join(ch for ch in rate_str if ch.isdigit() or ch == ".")
                unit_rate = float(rate_digits) if rate_digits else 0.0
            except ValueError:
                pass

            sku_derived = f"TALLY-{name.upper().replace(' ', '-')[:14]}"

            items.append({
                "sku": sku_derived,
                "name": name.strip(),
                "style_name": name.strip(),
                "category": parent_cat.strip() if parent_cat else "Tally Import",
                "stock": max(0, qty_num),
                "stock_count": max(0, qty_num),
                "unit_cost": unit_rate if unit_rate > 0 else 100.0,
                "retail_price": round(unit_rate * 1.4, 2) if unit_rate > 0 else 150.0,
                "reorder_point": 10,
                "location": "Main Warehouse"
            })

        # 2. Search for VOUCHER (Sales Vouchers)
        for v_node in root.findall(".//VOUCHER"):
            v_type = v_node.get("VOUCHERTYPENAME") or v_node.findtext("VOUCHERTYPENAME") or v_node.get("VTYPE") or "Sales"
            v_date = v_node.findtext("DATE") or v_node.get("DATE") or datetime.now().strftime("%Y%m%d")

            # Format YYYYMMDD to YYYY-MM-DD
            if len(v_date) == 8 and v_date.isdigit():
                v_date = f"{v_date[:4]}-{v_date[4:6]}-{v_date[6:]}"
            else:
                v_date = datetime.now().strftime("%Y-%m-%d")

            if "sale" in v_type.lower() or not v_type:
                inv_nodes = (
                    v_node.findall(".//ALLINVENTORYENTRIES") +
                    v_node.findall(".//INVENTORYENTRIES") +
                    v_node.findall(".//ALLINVENTORYENTRIES.LIST")
                )
                if not inv_nodes:
                    inv_nodes = [v_node]

                for inv_node in inv_nodes:
                    p_name = inv_node.findtext("STOCKITEMNAME") or inv_node.get("STOCKITEMNAME") or "Unknown"
                    if p_name == "Unknown":
                        continue
                    qty_str = inv_node.findtext("ACTUALQTY") or inv_node.findtext("BILLEDQTY") or inv_node.get("QTY") or "0"
                    qty_num = 0
                    try:
                        digits = "".join(ch for ch in qty_str if ch.isdigit() or ch == "-")
                        qty_num = abs(int(digits)) if digits and digits != "-" else 0
                    except ValueError:
                        pass

                    sku_derived = f"TALLY-{p_name.upper().replace(' ', '-')[:14]}"

                    vouchers.append({
                        "sku": sku_derived,
                        "product_name": p_name.strip(),
                        "units_sold": max(1, qty_num),
                        "quantity": max(1, qty_num),
                        "sale_date": v_date,
                        "channel": "Tally POS"
                    })

    except Exception as e:
        logger.error(f"Tally XML parsing error: {e}")
        raise ValueError(f"Invalid Tally XML format: {e}")

    return {
        "stock_items": items,
        "sales_vouchers": vouchers
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tally -> Excel Export Engine (Generates live_data/ files)
# ─────────────────────────────────────────────────────────────────────────────

def export_tally_to_excel_files(
    parsed_data: Dict[str, Any],
    live_data_dir: str = "live_data"
) -> Dict[str, Any]:
    """
    Transforms parsed Tally stock and sales data into normalized Excel spreadsheets
    saved directly into the live_data/ folder (inventory.xlsx, sales.xlsx, products.xlsx).
    This enables InsightOS's existing Excel Sync engine to ingest the data seamlessly.
    """
    if not os.path.isabs(live_data_dir):
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        live_data_dir = os.path.join(project_dir, live_data_dir)

    os.makedirs(live_data_dir, exist_ok=True)

    stock_items = parsed_data.get("stock_items", [])
    sales_vouchers = parsed_data.get("sales_vouchers", [])

    files_written = []

    # 1. Write / Update live_data/inventory.xlsx
    if stock_items:
        inv_path = os.path.join(live_data_dir, "inventory.xlsx")
        inv_records = []
        for it in stock_items:
            inv_records.append({
                "SKU": it["sku"],
                "Stock_Count": it["stock_count"],
                "Reorder_Point": it.get("reorder_point", 10),
                "Location": it.get("location", "Main Warehouse"),
                "Last_Restocked_At": datetime.now().strftime("%Y-%m-%d")
            })

        df_inv = pd.DataFrame(inv_records)
        with pd.ExcelWriter(inv_path, engine="openpyxl") as writer:
            df_inv.to_excel(writer, sheet_name="Inventory", index=False)
        files_written.append("inventory.xlsx")

        # 2. Write / Update live_data/products.xlsx (Catalog)
        prod_path = os.path.join(live_data_dir, "products.xlsx")
        prod_records = []
        for it in stock_items:
            prod_records.append({
                "SKU": it["sku"],
                "Style_Name": it["style_name"],
                "Category": it["category"],
                "Unit_Cost": it["unit_cost"],
                "Retail_Price": it["retail_price"],
                "Supplier_ID": "SUP-TALLY-01"
            })

        df_prod = pd.DataFrame(prod_records)
        with pd.ExcelWriter(prod_path, engine="openpyxl") as writer:
            df_prod.to_excel(writer, sheet_name="Products", index=False)
        files_written.append("products.xlsx")

    # 3. Write / Update live_data/sales.xlsx (Transactions)
    if sales_vouchers:
        sales_path = os.path.join(live_data_dir, "sales.xlsx")
        sales_records = []
        for sv in sales_vouchers:
            sales_records.append({
                "SKU": sv["sku"],
                "Units_Sold": sv["units_sold"],
                "Sale_Date": sv["sale_date"],
                "Channel": sv.get("channel", "Tally POS")
            })

        df_sales = pd.DataFrame(sales_records)
        with pd.ExcelWriter(sales_path, engine="openpyxl") as writer:
            df_sales.to_excel(writer, sheet_name="Sales", index=False)
        files_written.append("sales.xlsx")

    logger.info(f"[Tally Export] Successfully generated {len(files_written)} Excel file(s) in {live_data_dir}")

    return {
        "status": "SUCCESS",
        "destination": live_data_dir,
        "files_written": files_written,
        "stock_items_count": len(stock_items),
        "sales_vouchers_count": len(sales_vouchers),
        "generated_at": datetime.now().isoformat()
    }


# ─────────────────────────────────────────────────────────────────────────────
# Automated End-to-End Tally Pull & Ingestion Workflow
# ─────────────────────────────────────────────────────────────────────────────

def auto_sync_tally(
    host: str = "localhost",
    port: int = 9000,
    company: Optional[str] = None,
    live_data_dir: str = "live_data",
    db_path: str = "retail_clothing.db"
) -> Dict[str, Any]:
    """
    Executes the complete automated Tally -> InsightOS data flow:
    1. Tests connection to Tally XML server.
    2. Fetches Stock Summary & Sales Vouchers XML from Tally.
    3. Transforms and exports into normalized Excel files in live_data/.
    4. Triggers Excel Sync to ingest into SQLite database.
    5. Recomputes Auto Insights and dispatches notifications.
    """
    logger.info(f"[Tally Auto-Sync] Initiating automated sync from Tally ({host}:{port})...")

    # Step 1: Ping Tally
    ping_res = ping_tally_server(host=host, port=port)
    if not ping_res.get("online"):
        err_msg = ping_res.get("error") or "Tally server offline"
        logger.warning(f"[Tally Auto-Sync] Tally server unreachable at {host}:{port}: {err_msg}")
        return {
            "status": "OFFLINE",
            "message": f"Tally is not reachable at http://{host}:{port}. Skipping automated pull.",
            "tally_ping": ping_res,
            "timestamp": datetime.now().isoformat()
        }

    try:
        # Step 2: Fetch Stock Summary XML
        stock_req = build_tally_stock_request_xml(company=company)
        stock_xml = fetch_tally_xml_via_http(stock_req, host=host, port=port)
        parsed_stock = parse_tally_xml(stock_xml)

        # Step 3: Fetch Sales Vouchers XML
        sales_req = build_tally_sales_request_xml(company=company)
        try:
            sales_xml = fetch_tally_xml_via_http(sales_req, host=host, port=port)
            parsed_sales = parse_tally_xml(sales_xml)
        except Exception as e_sales:
            logger.warning(f"[Tally Auto-Sync] Voucher register fetch failed (using stock only): {e_sales}")
            parsed_sales = {"sales_vouchers": []}

        # Merge parsed results
        unified_parsed = {
            "stock_items": parsed_stock.get("stock_items", []),
            "sales_vouchers": parsed_sales.get("sales_vouchers", [])
        }

        # Step 4: Export to Excel in live_data/ folder
        excel_res = export_tally_to_excel_files(unified_parsed, live_data_dir=live_data_dir)

        # Step 5: Trigger InsightOS Excel Sync (force=True to process immediately)
        sync_res = sync_excel_to_db(db_path=db_path, live_data_dir=live_data_dir, force=True)

        return {
            "status": "SUCCESS",
            "source": f"TALLY_HTTP_{host}_{port}",
            "stock_items_fetched": len(unified_parsed["stock_items"]),
            "sales_vouchers_fetched": len(unified_parsed["sales_vouchers"]),
            "excel_export": excel_res,
            "db_sync": sync_res,
            "synced_at": datetime.now().isoformat()
        }

    except Exception as exc:
        logger.error(f"[Tally Auto-Sync] Error during automated sync: {exc}")
        return {
            "status": "FAILED",
            "error": str(exc),
            "timestamp": datetime.now().isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# Direct XML Sync (Fallback / Manual Upload)
# ─────────────────────────────────────────────────────────────────────────────

def sync_tally_xml_to_db(xml_content: str, db_path: str = "retail_clothing.db") -> Dict[str, Any]:
    """
    Ingest Tally XML payload directly into SQLite database (products, inventory, sales).
    Retained for backward-compatible manual file uploads and API pushes.
    """
    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    parsed = parse_tally_xml(xml_content)
    items = parsed.get("stock_items", [])
    vouchers = parsed.get("sales_vouchers", [])

    rows_synced = 0
    cursor = conn.cursor()

    try:
        # Check inventory table schema
        pragma_inv = cursor.execute("PRAGMA table_info(inventory)").fetchall()
        inv_cols = {row[1] for row in pragma_inv}
        stock_col = "stock_count" if "stock_count" in inv_cols else ("current_stock" if "current_stock" in inv_cols else "stock")
        pk_inv = "sku" if "sku" in inv_cols else "product_id"

        # Check products table schema
        pragma_p = cursor.execute("PRAGMA table_info(products)").fetchall()
        p_cols = {row[1] for row in pragma_p}
        name_col = "style_name" if "style_name" in p_cols else "name"
        pk_p = "sku" if "sku" in p_cols else "product_id"

        # Upsert stock items
        for item in items:
            p_name = item["name"]
            stock_val = item["stock"]
            p_sku = item.get("sku", f"TALLY-{p_name.upper().replace(' ', '-')[:12]}")

            existing_p = cursor.execute(
                f"SELECT {pk_p} FROM products WHERE {pk_p} = ? OR {name_col} = ?",
                (p_sku, p_name)
            ).fetchone()

            if not existing_p:
                p_fields = {pk_p: p_sku, name_col: p_name}
                if "category" in p_cols: p_fields["category"] = item.get("category", "Tally Import")
                if "size" in p_cols: p_fields["size"] = item.get("size", "M")
                if "color" in p_cols: p_fields["color"] = item.get("color", "Standard")
                if "unit_cost" in p_cols: p_fields["unit_cost"] = item.get("unit_cost", 50.0)
                if "retail_price" in p_cols: p_fields["retail_price"] = item.get("retail_price", 100.0)
                if "supplier_id" in p_cols: p_fields["supplier_id"] = item.get("supplier_id", "SUP-0001")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if "created_at" in p_cols: p_fields["created_at"] = now_str
                if "updated_at" in p_cols: p_fields["updated_at"] = now_str
                
                cols_str = ", ".join(p_fields.keys())
                placeholders = ", ".join(["?"] * len(p_fields))
                cursor.execute(f"INSERT INTO products ({cols_str}) VALUES ({placeholders})", list(p_fields.values()))

            # Upsert inventory
            existing_inv = cursor.execute(f"SELECT {pk_inv} FROM inventory WHERE {pk_inv} = ?", (p_sku,)).fetchone()
            if existing_inv:
                if "updated_at" in inv_cols:
                    cursor.execute(f"UPDATE inventory SET {stock_col} = ?, updated_at = ? WHERE {pk_inv} = ?", (stock_val, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_sku))
                else:
                    cursor.execute(f"UPDATE inventory SET {stock_col} = ? WHERE {pk_inv} = ?", (stock_val, p_sku))
            else:
                inv_fields = {pk_inv: p_sku, stock_col: stock_val}
                if "reorder_point" in inv_cols: inv_fields["reorder_point"] = 10
                if "warehouse_id" in inv_cols: inv_fields["warehouse_id"] = "WH-TALLY-01"
                elif "location" in inv_cols: inv_fields["location"] = "Main Warehouse"
                if "created_at" in inv_cols: inv_fields["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if "updated_at" in inv_cols: inv_fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cols_str = ", ".join(inv_fields.keys())
                placeholders = ", ".join(["?"] * len(inv_fields))
                cursor.execute(f"INSERT INTO inventory ({cols_str}) VALUES ({placeholders})", list(inv_fields.values()))

            rows_synced += 1

        # Sales records
        pragma_sales = cursor.execute("PRAGMA table_info(sales_events)").fetchall()
        sales_table = "sales_events" if pragma_sales else "sales"
        pragma_s_cols = cursor.execute(f"PRAGMA table_info('{sales_table}')").fetchall()
        s_col_names = {row[1] for row in pragma_s_cols}

        for idx, v in enumerate(vouchers):
            p_sku = v.get("sku", f"TALLY-{v['product_name'].upper().replace(' ', '-')[:12]}")
            qty = v["units_sold"]
            s_date = v["sale_date"]
            event_id = f"TALLY-SE-{int(time.time())}-{idx+1:04d}"

            s_fields = {}
            if "event_id" in s_col_names: s_fields["event_id"] = event_id
            if "sku" in s_col_names: s_fields["sku"] = p_sku
            elif "product_id" in s_col_names: s_fields["product_id"] = p_sku
            if "units_sold" in s_col_names: s_fields["units_sold"] = qty
            elif "quantity" in s_col_names: s_fields["quantity"] = qty
            if "sale_price" in s_col_names: s_fields["sale_price"] = 100.0
            if "sale_date" in s_col_names: s_fields["sale_date"] = s_date
            elif "transaction_date" in s_col_names: s_fields["transaction_date"] = s_date
            if "channel" in s_col_names: s_fields["channel"] = "Tally POS"
            if "store_id" in s_col_names: s_fields["store_id"] = "STORE-TALLY"

            cols_str = ", ".join(s_fields.keys())
            placeholders = ", ".join(["?"] * len(s_fields))
            cursor.execute(f"INSERT INTO {sales_table} ({cols_str}) VALUES ({placeholders})", list(s_fields.values()))
            rows_synced += 1

        cursor.execute(
            "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('TALLY', 'XML_DIRECT', 'SUCCESS', ?)",
            (rows_synced,)
        )
        conn.commit()

        if rows_synced > 0:
            generate_insights(db_path)

        return {
            "status": "SUCCESS",
            "source": "TALLY_XML",
            "stock_items_synced": len(items),
            "vouchers_synced": len(vouchers),
            "rows_synced": rows_synced,
            "synced_at": datetime.now().isoformat()
        }
    except Exception as e:
        conn.rollback()
        logger.error(f"Tally XML DB ingestion failed: {e}")
        cursor.execute(
            "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('TALLY', 'XML_DIRECT', 'FAILED', 0, ?)",
            (str(e),)
        )
        conn.commit()
        raise e
    finally:
        conn.close()
