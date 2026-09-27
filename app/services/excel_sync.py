"""
Excel Sync Service for InsightOS.
Monitors the live_data/ directory for updated/new Excel files and syncs them
into the InsightOS SQLite database.
Supports:
1. Multi-sheet Excel files (Products, Inventory, Sales, Suppliers)
2. Unified single-sheet transactional datasets (Sales + Products in one sheet)
3. Direct full-column retail transaction ingestion (shop_sales table)
4. Dynamic schema mapping and automatic inventory baseline creation
"""

import os
import re
import json
import sqlite3
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from app.core.logger import logger
from app.services.auto_insights import generate_insights, get_db_connection


def init_sync_schema(conn: sqlite3.Connection):
    """Ensure sync_logs and shop_sales tables exist in database."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,         -- 'EXCEL' or 'TALLY'
            file_name TEXT,
            status TEXT NOT NULL,              -- 'SUCCESS', 'FAILED', 'SKIPPED'
            rows_synced INTEGER DEFAULT 0,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shop_sales (
            transaction_id TEXT PRIMARY KEY,
            date TEXT,
            shop_id TEXT,
            shop_name TEXT,
            category TEXT,
            city TEXT,
            product TEXT,
            quantity INTEGER,
            unit_price REAL,
            sales REAL,
            cost REAL,
            profit REAL,
            payment_method TEXT,
            customer_type TEXT,
            source TEXT DEFAULT 'excel'
        );
    """)
    conn.commit()


def get_sync_metadata(metadata_path: str) -> Dict[str, float]:
    """Load cached file modification timestamps from .sync_metadata.json."""
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read sync metadata: {e}")
    return {}


def save_sync_metadata(metadata_path: str, data: Dict[str, float]):
    """Save updated file modification timestamps to .sync_metadata.json."""
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save sync metadata: {e}")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame headers, promote header row if sheet starts with a banner, and strip whitespace."""
    if df.empty:
        return df
    
    df = df.copy()
    # Check if headers are generic (e.g. Unnamed / Banner) and row 0 or 1 contains 'SKU' or 'Product' or 'Transaction'
    cols_str = " ".join([str(c).lower() for c in df.columns])
    if not any(k in cols_str for k in ("sku", "product", "transaction_id", "transaction id")):
        for r_idx in range(min(4, len(df))):
            row_vals = [str(x).lower().strip() for x in df.iloc[r_idx].values]
            if any(k in row_vals for k in ("sku", "product", "item", "transaction_id", "transaction id")):
                new_cols = [str(x).strip() if pd.notnull(x) else f"col_{i}" for i, x in enumerate(df.iloc[r_idx].values)]
                df = df.iloc[r_idx + 1:].copy().reset_index(drop=True)
                df.columns = new_cols
                break

    # Normalize column names: lowercase, strip, replace spaces/dashes with underscores
    clean_cols = []
    for c in df.columns:
        norm = str(c).lower().strip().replace(" ", "_").replace("-", "_").replace(".", "")
        clean_cols.append(norm)
    df.columns = clean_cols
    return df


def _clean_num(val: Any, default: float = 0.0) -> float:
    """Clean string number containing $, commas, or currency symbols into float."""
    if val is None or pd.isna(val):
        return default
    s = str(val).replace("$", "").replace("₹", "").replace(",", "").replace("€", "").replace("£", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _clean_sku(val: Any, name: Any = "") -> str:
    """Generate or clean SKU identifier deterministically."""
    s_val = str(val).strip() if val is not None and pd.notnull(val) else ""
    if s_val and s_val.lower() not in ("nan", "none", "", "null", "undefined", "sku"):
        return s_val
    s_name = str(name).strip() if name is not None and pd.notnull(name) else ""
    if s_name and s_name.lower() not in ("nan", "none", "", "null", "undefined"):
        clean = re.sub(r'[^A-Za-z0-9]+', '-', s_name).strip('-').upper()
        return f"SKU-{clean}" if not clean.startswith("SKU-") else clean
    return "SKU-UNKNOWN"


def _upsert_shop_sales(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert full retail dataset with all columns into shop_sales table."""
    df_norm = _normalize_df(df)
    cols = list(df_norm.columns)
    
    has_txn = any(c in cols for c in ("transaction_id", "order_id", "invoice_no", "date", "product", "sales", "quantity"))
    if not has_txn:
        return 0

    cursor = conn.cursor()
    count = 0

    id_src = next((c for c in cols if c in ("transaction_id", "order_id", "invoice_no", "id", "event_id")), None)
    date_src = next((c for c in cols if c in ("date", "sale_date", "transaction_date", "timestamp")), None)
    shop_id_src = next((c for c in cols if c in ("shop_id", "store_id")), None)
    shop_name_src = next((c for c in cols if c in ("shop_name", "store_name", "store", "shop", "vendor", "channel")), None)
    cat_src = next((c for c in cols if c in ("category", "product_category", "department")), None)
    city_src = next((c for c in cols if c in ("city", "location", "region")), None)
    prod_src = next((c for c in cols if c in ("product", "product_name", "item", "item_name", "style_name")), None)
    qty_src = next((c for c in cols if c in ("quantity", "qty", "units_sold", "count")), None)
    price_src = next((c for c in cols if c in ("unit_price", "price", "selling_price", "retail_price")), None)
    sales_src = next((c for c in cols if c in ("sales", "total_sales", "revenue", "total_revenue", "amount")), None)
    cost_src = next((c for c in cols if c in ("cost", "total_cost", "unit_cost")), None)
    profit_src = next((c for c in cols if c in ("profit", "net_profit", "margin")), None)
    pay_src = next((c for c in cols if c in ("payment_method", "payment", "payment_type")), None)
    cust_src = next((c for c in cols if c in ("customer_type", "customer", "type")), None)

    for idx, row in df_norm.iterrows():
        txn_id = str(row.get(id_src, f"T{idx+1:03d}")).strip() if id_src and pd.notnull(row.get(id_src)) else f"T{idx+1:03d}"
        if not txn_id or txn_id.lower() in ("nan", "none", "", "total", "summary"):
            continue

        p_name = str(row.get(prod_src, f"Item-{idx+1}")).strip() if prod_src and pd.notnull(row.get(prod_src)) else f"Item-{idx+1}"
        cat = str(row.get(cat_src, "General")).strip() if cat_src and pd.notnull(row.get(cat_src)) else "General"
        shop_id = str(row.get(shop_id_src, "S001")).strip() if shop_id_src and pd.notnull(row.get(shop_id_src)) else "S001"
        shop_name = str(row.get(shop_name_src, "Main Store")).strip() if shop_name_src and pd.notnull(row.get(shop_name_src)) else "Main Store"
        city = str(row.get(city_src, "Global")).strip() if city_src and pd.notnull(row.get(city_src)) else "Global"
        
        qty = int(_clean_num(row.get(qty_src, 1), 1.0))
        unit_price = _clean_num(row.get(price_src, 0.0), 0.0)
        sales = _clean_num(row.get(sales_src, unit_price * qty), unit_price * qty)
        cost = _clean_num(row.get(cost_src, 0.0), 0.0)
        profit = _clean_num(row.get(profit_src, sales - cost), sales - cost)
        pay_method = str(row.get(pay_src, "Card")).strip() if pay_src and pd.notnull(row.get(pay_src)) else "Card"
        cust_type = str(row.get(cust_src, "New")).strip() if cust_src and pd.notnull(row.get(cust_src)) else "New"
        dt = str(row.get(date_src, datetime.now().strftime("%Y-%m-%d"))).strip() if date_src and pd.notnull(row.get(date_src)) else datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT OR REPLACE INTO shop_sales (
                transaction_id, date, shop_id, shop_name, category, city,
                product, quantity, unit_price, sales, cost, profit,
                payment_method, customer_type, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel')
        """, (txn_id, dt, shop_id, shop_name, cat, city, p_name, qty, unit_price, sales, cost, profit, pay_method, cust_type))
        count += 1

    conn.commit()
    return count


def _upsert_products(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert products from DataFrame into products table dynamically based on DB schema."""
    df = _normalize_df(df)
    cols = list(df.columns)

    cursor = conn.cursor()
    pragma_p = cursor.execute("PRAGMA table_info(products)").fetchall()
    if not pragma_p:
        logger.warning("products table does not exist in DB")
        return 0
    db_cols = {row[1]: {"type": row[2], "notnull": row[3], "pk": row[5]} for row in pragma_p}

    pk_col = next((col for col, info in db_cols.items() if info["pk"] == 1), "sku" if "sku" in db_cols else "product_id")

    id_source = next((cand for cand in ("sku", "product_id", "product_code", "item_id", "item_code") if cand in cols), None)
    name_source = next((cand for cand in ("product_name", "style_name", "name", "item_name", "title", "description", "product", "item") if cand in cols), None)
    cat_source = next((cand for cand in ("category", "product_category", "department", "group", "product_type") if cand in cols), None)
    cost_source = next((cand for cand in ("cost_price", "unit_cost", "cost", "purchase_price", "buy_price") if cand in cols), None)
    price_source = next((cand for cand in ("selling_price", "retail_price", "price", "sale_price", "unit_price", "mrp", "sales") if cand in cols), None)
    supplier_source = next((cand for cand in ("supplier", "supplier_id", "vendor", "vendor_name", "shop_name", "shop_id") if cand in cols), None)

    count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    seen_skus = set()

    for idx, row in df.iterrows():
        p_name = str(row.get(name_source, "")).strip() if name_source and pd.notnull(row.get(name_source)) else ""
        raw_id = row.get(id_source) if id_source else None
        p_id = _clean_sku(raw_id, p_name if p_name else f"Item-{idx+1:04d}")

        if not p_id or p_id.lower() in ("nan", "sku", "none", "", "total", "summary") or p_id in seen_skus:
            continue
        seen_skus.add(p_id)

        if not p_name:
            p_name = f"Item {p_id}"

        existing = cursor.execute(f"SELECT {pk_col} FROM products WHERE {pk_col} = ?", (p_id,)).fetchone()
        if not existing and "style_name" in db_cols:
            existing = cursor.execute("SELECT sku FROM products WHERE style_name = ?", (p_name,)).fetchone()

        unit_cost_val = _clean_num(row.get(cost_source), 10.0) if cost_source else 10.0
        retail_price_val = _clean_num(row.get(price_source), 25.0) if price_source else 25.0
        cat_val = str(row.get(cat_source, "General")).strip() if cat_source and pd.notnull(row.get(cat_source)) else "General"
        supp_val = str(row.get(supplier_source, "Global Direct")).strip() if supplier_source and pd.notnull(row.get(supplier_source)) else "Global Direct"

        fields = {}
        for col, info in db_cols.items():
            if col in ("sku", "product_id"):
                fields[col] = p_id
            elif col in ("style_name", "name"):
                fields[col] = p_name
            elif col == "unit_cost":
                fields[col] = unit_cost_val
            elif col == "retail_price":
                fields[col] = retail_price_val
            elif col == "category":
                fields[col] = cat_val
            elif col == "supplier_id":
                fields[col] = supp_val
            elif col == "source":
                fields[col] = "excel"
            elif col in cols and pd.notnull(row.get(col)):
                fields[col] = row.get(col)
            elif info["notnull"] == 1:
                if col == "size": fields[col] = "M"
                elif col == "color": fields[col] = "Standard"
                elif col == "created_at": fields[col] = today_str

        # Ensure supplier exists in suppliers table
        if supp_val:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO suppliers (supplier_id, supplier_name, lead_time_days, on_time_rate, country, source)
                    VALUES (?, ?, 7, 0.95, 'Global', 'excel')
                """, (supp_val, supp_val))
            except Exception:
                pass

        if existing:
            key_val = existing[0]
            update_set = ", ".join([f"{k} = ?" for k in fields.keys() if k != pk_col])
            if update_set:
                vals = [fields[k] for k in fields.keys() if k != pk_col] + [key_val]
                cursor.execute(f"UPDATE products SET {update_set} WHERE {pk_col} = ?", vals)
        else:
            col_names = ", ".join(fields.keys())
            placeholders = ", ".join(["?"] * len(fields))
            cursor.execute(f"INSERT INTO products ({col_names}) VALUES ({placeholders})", list(fields.values()))

        reorder_src = next((c for c in cols if c in ("reorder_level", "reorder_point", "reorder")), None)
        if reorder_src and pd.notnull(row.get(reorder_src)):
            reorder_val = int(_clean_num(row.get(reorder_src), 15.0))
            try:
                inv_row = cursor.execute("SELECT sku FROM inventory WHERE sku = ?", (p_id,)).fetchone()
                if inv_row:
                    cursor.execute("UPDATE inventory SET reorder_point = ? WHERE sku = ?", (reorder_val, p_id))
                else:
                    cursor.execute("INSERT OR IGNORE INTO inventory (sku, location, stock_count, reorder_point, last_restocked_at, source) VALUES (?, 'Main Warehouse', 0, ?, ?, 'excel')", (p_id, reorder_val, today_str))
            except Exception:
                pass

        count += 1

    conn.commit()
    return count


def _upsert_inventory(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert inventory levels from DataFrame into inventory table dynamically."""
    df = _normalize_df(df)
    cols = list(df.columns)

    cursor = conn.cursor()
    pragma_i = cursor.execute("PRAGMA table_info(inventory)").fetchall()
    if not pragma_i:
        logger.warning("inventory table does not exist in DB")
        return 0
    db_cols = {row[1]: {"type": row[2], "notnull": row[3], "pk": row[5]} for row in pragma_i}

    pk_col = next((col for col, info in db_cols.items() if info["pk"] == 1), "sku" if "sku" in db_cols else "product_id")

    id_candidates = ["sku", "product_id", "item_id", "product_code"]
    id_source = next((cand for cand in id_candidates if cand in cols), None)
    name_source = next((cand for cand in ("product_name", "style_name", "name", "product", "item") if cand in cols), None)

    stock_candidates = [
        "current_stock", "units_in_stock", "col_5", "stock_count", "stock",
        "total_units_in_stock", "inventory_level", "quantity", "qty", "col_3"
    ]
    stock_source = next((cand for cand in stock_candidates if cand in cols), None)

    reorder_candidates = ["reorder_point", "reorder_level", "reorder", "min_stock", "safety_stock"]
    reorder_source = next((cand for cand in reorder_candidates if cand in cols), None)

    loc_candidates = ["location", "warehouse_location", "warehouse", "store_location", "shop_name", "city"]
    loc_source = next((cand for cand in loc_candidates if cand in cols), None)

    if not id_source and not name_source:
        logger.warning("Inventory sheet missing product_id/sku/name column")
        return 0

    count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")

    for idx, row in df.iterrows():
        p_name = str(row.get(name_source, "")).strip() if name_source and pd.notnull(row.get(name_source)) else ""
        raw_id = row.get(id_source) if id_source else None
        p_id = _clean_sku(raw_id, p_name)

        if not p_id or p_id.lower() in ("nan", "sku", "none", "", "total", "summary"):
            continue

        raw_stock = row.get(stock_source) if stock_source else 0
        stock_val = int(_clean_num(raw_stock, 0.0))
        raw_reorder = row.get(reorder_source) if reorder_source else 15
        reorder_val = int(_clean_num(raw_reorder, 15.0))
        loc_val = str(row.get(loc_source, "Main Warehouse")).strip() if loc_source and pd.notnull(row.get(loc_source)) else "Main Warehouse"

        existing = cursor.execute(f"SELECT {pk_col} FROM inventory WHERE {pk_col} = ?", (p_id,)).fetchone()

        fields = {}
        for col, info in db_cols.items():
            if col in ("sku", "product_id"):
                fields[col] = p_id
            elif col in ("stock_count", "current_stock", "stock"):
                fields[col] = stock_val
            elif col == "reorder_point":
                if reorder_source:
                    fields[col] = reorder_val
                elif not existing:
                    fields[col] = 15
            elif col == "location":
                fields[col] = loc_val
            elif col == "source":
                fields[col] = "excel"
            elif col in cols and pd.notnull(row.get(col)):
                fields[col] = row.get(col)
            elif info["notnull"] == 1:
                if col == "location": fields[col] = "Main Warehouse"
                elif col == "last_restocked_at": fields[col] = today_str

        if existing:
            update_set = ", ".join([f"{k} = ?" for k in fields.keys() if k != pk_col])
            if update_set:
                vals = [fields[k] for k in fields.keys() if k != pk_col] + [p_id]
                cursor.execute(f"UPDATE inventory SET {update_set} WHERE {pk_col} = ?", vals)
        else:
            col_names = ", ".join(fields.keys())
            placeholders = ", ".join(["?"] * len(fields))
            cursor.execute(f"INSERT INTO inventory ({col_names}) VALUES ({placeholders})", list(fields.values()))
        count += 1

    conn.commit()
    return count


def _upsert_sales(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert/Insert sales events into sales_events or sales table dynamically based on DB schema."""
    df = _normalize_df(df)
    cols = list(df.columns)

    cursor = conn.cursor()
    pragma_se = cursor.execute("PRAGMA table_info(sales_events)").fetchall()
    sales_table = "sales_events" if pragma_se else "sales"
    pragma_s = cursor.execute(f"PRAGMA table_info('{sales_table}')").fetchall()
    if not pragma_s:
        logger.warning("Sales table does not exist in DB")
        return 0
    db_cols = {row[1]: {"type": row[2], "notnull": row[3], "pk": row[5]} for row in pragma_s}

    id_source = next((c for c in cols if c in ("sku", "product_id", "item_id", "product_code")), None)
    name_source = next((c for c in cols if c in ("product", "item", "product_name", "style_name", "name")), None)
    qty_source = next((c for c in cols if c in ("quantity_sold", "units_sold", "quantity", "qty", "count")), None)
    price_source = next((c for c in cols if c in ("unit_price", "unit_sale_price", "selling_price", "price", "sales")), None)
    date_source = next((c for c in cols if c in ("date", "sale_date", "timestamp", "transaction_date")), None)
    channel_source = next((c for c in cols if c in ("channel", "payment_method", "sales_channel", "shop_name", "city")), None)
    event_id_source = next((c for c in cols if c in ("transaction_id", "event_id", "order_id", "invoice_no")), None)

    if (not id_source and not name_source) or not qty_source:
        logger.warning("Sales sheet missing product/sku or quantity column")
        return 0

    count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_ts = int(time.time())

    for idx, row in df.iterrows():
        p_name = str(row.get(name_source, "")).strip() if name_source and pd.notnull(row.get(name_source)) else ""
        raw_id = row.get(id_source) if id_source else None
        p_id = _clean_sku(raw_id, p_name)

        if not p_id or p_id.lower() in ("nan", "sku", "none", ""):
            continue

        qty_val = int(_clean_num(row.get(qty_source), 1.0))
        unit_price_val = _clean_num(row.get(price_source), 25.0) if price_source else 25.0
        s_date = str(row.get(date_source, today_str)).strip() if date_source and pd.notnull(row.get(date_source)) else today_str
        channel_val = str(row.get(channel_source, "Online")).strip() if channel_source and pd.notnull(row.get(channel_source)) else "Online"
        e_id = str(row.get(event_id_source)).strip() if event_id_source and pd.notnull(row.get(event_id_source)) else f"SE-{now_ts}-{idx+1:04d}"

        fields = {}
        for col, info in db_cols.items():
            if col in ("sku", "product_id"):
                fields[col] = p_id
            elif col in ("units_sold", "quantity", "qty", "quantity_sold"):
                fields[col] = qty_val
            elif col in ("unit_sale_price", "unit_price", "price"):
                fields[col] = unit_price_val
            elif col in ("sale_date", "date", "timestamp"):
                fields[col] = s_date
            elif col == "channel":
                fields[col] = channel_val
            elif col in ("event_id", "sale_id", "transaction_id"):
                fields[col] = e_id
            elif col == "source":
                fields[col] = "excel"
            elif col in cols and pd.notnull(row.get(col)):
                fields[col] = row.get(col)
            elif info["notnull"] == 1 and info["pk"] == 0:
                if col == "channel": fields[col] = "Online"
                elif col == "store_id": fields[col] = "STORE-ONLINE"

        col_names = ", ".join(fields.keys())
        placeholders = ", ".join(["?"] * len(fields))
        cursor.execute(f"INSERT OR REPLACE INTO {sales_table} ({col_names}) VALUES ({placeholders})", list(fields.values()))
        count += 1

    conn.commit()
    return count


def _ensure_inventory_baseline(conn: sqlite3.Connection):
    """Ensure every product in products table has an inventory baseline if none exists."""
    cursor = conn.cursor()
    products = cursor.execute("SELECT sku FROM products").fetchall()
    today_str = datetime.now().strftime("%Y-%m-%d")
    for idx, (sku,) in enumerate(products):
        existing = cursor.execute("SELECT sku FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if not existing:
            # Check sales total for sku to estimate realistic stock
            sales_sum = cursor.execute("SELECT SUM(units_sold) FROM sales_events WHERE sku = ?", (sku,)).fetchone()[0] or 10
            if idx % 4 == 0:
                reorder = max(int(sales_sum * 1.5), 15)
                stock = max(int(sales_sum * 0.4), 4)
            else:
                reorder = max(int(sales_sum * 0.8), 10)
                stock = max(int(sales_sum * 2.5), 25)

            cursor.execute("""
                INSERT INTO inventory (sku, location, stock_count, reorder_point, last_restocked_at, source)
                VALUES (?, 'Main Warehouse', ?, ?, ?, 'excel')
            """, (sku, stock, reorder, today_str))
    conn.commit()


def sync_excel_to_db(db_path: str = "retail_clothing.db", live_data_dir: str = "live_data", force: bool = False) -> Dict[str, Any]:
    """
    Scans live_data_dir for Excel files (.xlsx, .xls) and syncs new/updated data into SQLite.
    Tracks file modification timestamps to prevent redundant processing.
    Handles locked/busy files gracefully.
    Triggers generate_insights() upon successful data sync.
    """
    if not os.path.isabs(live_data_dir):
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        live_data_dir = os.path.join(project_dir, live_data_dir)

    os.makedirs(live_data_dir, exist_ok=True)
    metadata_path = os.path.join(live_data_dir, ".sync_metadata.json")
    meta = get_sync_metadata(metadata_path)

    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    files_processed = []
    total_rows = 0
    errors = []

    excel_files = [
        f for f in os.listdir(live_data_dir)
        if (f.endswith(".xlsx") or f.endswith(".xls")) and not f.startswith("~$")
    ]

    if not excel_files:
        logger.info(f"📁 [Excel Sync] No Excel files found in {live_data_dir}")
        conn.close()
        return {
            "status": "SKIPPED",
            "message": f"No Excel files found in {live_data_dir}",
            "files_processed": [],
            "rows_synced": 0,
            "synced_at": datetime.now().isoformat()
        }

    for file_name in excel_files:
        file_path = os.path.join(live_data_dir, file_name)
        try:
            mtime = os.path.getmtime(file_path)
            last_mtime = meta.get(file_name, 0.0)

            # Skip if file hasn't been modified (unless force=True)
            if not force and mtime <= last_mtime:
                continue

            logger.info(f"[Excel Sync] Processing updated file: {file_name}")

            # Read Excel file with pandas/openpyxl
            excel_data = pd.read_excel(file_path, sheet_name=None)
            file_rows = 0

            for sheet_name, df in excel_data.items():
                if df.empty:
                    continue

                sheet_lower = sheet_name.lower().strip()
                cols = [str(c).lower().strip() for c in df.columns]

                # Always upsert full retail transactions into shop_sales table if present
                r_shop = _upsert_shop_sales(conn, df)
                if r_shop > 0:
                    file_rows += r_shop

                if "product" in sheet_lower:
                    r = _upsert_products(conn, df)
                    file_rows += r
                elif "inventory" in sheet_lower or "stock" in sheet_lower:
                    r = _upsert_inventory(conn, df)
                    file_rows += r
                elif "sale" in sheet_lower or "order" in sheet_lower:
                    if any(c in cols for c in ("product", "category", "product_name")):
                        _upsert_products(conn, df)
                    r = _upsert_sales(conn, df)
                    file_rows += r
                else:
                    # Inspect columns for unified or specific sheets
                    has_product = any(c in cols for c in ("product", "product_name", "item", "sku"))
                    has_sales = any(c in cols for c in ("quantity", "qty", "sales", "unit_price", "transaction_id", "units_sold"))
                    has_stock = any("stock" in c for c in cols)

                    if has_product and has_sales:
                        r_p = _upsert_products(conn, df)
                        r_s = _upsert_sales(conn, df)
                        file_rows += (r_p + r_s)
                    elif has_stock:
                        r = _upsert_inventory(conn, df)
                        file_rows += r
                    elif has_sales:
                        r = _upsert_sales(conn, df)
                        file_rows += r
                    elif has_product:
                        r = _upsert_products(conn, df)
                        file_rows += r

            _ensure_inventory_baseline(conn)

            meta[file_name] = mtime
            total_rows += file_rows
            files_processed.append(file_name)

            # Log success for file
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('EXCEL', ?, 'SUCCESS', ?)",
                (file_name, file_rows)
            )
            conn.commit()

        except PermissionError:
            err_msg = f"File {file_name} is locked/open in another program. Skipping."
            logger.warning(f"[Excel Sync] {err_msg}")
            errors.append(err_msg)
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('EXCEL', ?, 'SKIPPED', 0, ?)",
                (file_name, err_msg)
            )
            conn.commit()

        except Exception as exc:
            err_msg = f"Failed to sync {file_name}: {str(exc)}"
            logger.error(f"[Excel Sync] {err_msg}")
            errors.append(err_msg)
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('EXCEL', ?, 'FAILED', 0, ?)",
                (file_name, str(exc))
            )
            conn.commit()

    save_sync_metadata(metadata_path, meta)
    conn.close()

    status_str = "SUCCESS" if files_processed else ("SKIPPED" if not errors else "FAILED")

    # If any file was processed successfully, trigger auto insights regeneration
    if files_processed:
        try:
            logger.info("[Excel Sync] Data updated, triggering Auto-generated Insights refresh...")
            generate_insights(db_path)
        except Exception as e_ins:
            logger.warning(f"Auto insights refresh after sync warning: {e_ins}")

    return {
        "status": status_str,
        "files_processed": files_processed,
        "rows_synced": total_rows,
        "errors": errors,
        "synced_at": datetime.now().isoformat()
    }


def get_sync_status(db_path: str = "retail_clothing.db") -> Dict[str, Any]:
    """Retrieve last sync status and sync log history."""
    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    cursor = conn.cursor()

    # Get last sync log
    last_log = cursor.execute("""
        SELECT source_type, file_name, status, rows_synced, synced_at, error_message
        FROM sync_logs
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    # Get summary stats
    logs = cursor.execute("""
        SELECT source_type, file_name, status, rows_synced, synced_at, error_message
        FROM sync_logs
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    history = []
    for row in logs:
        history.append({
            "source_type": row[0],
            "file_name": row[1],
            "status": row[2],
            "rows_synced": row[3],
            "synced_at": str(row[4]),
            "error_message": row[5]
        })

    last_sync_info = None
    if last_log:
        last_sync_info = {
            "source_type": last_log[0],
            "file_name": last_log[1],
            "status": last_log[2],
            "rows_synced": last_log[3],
            "synced_at": str(last_log[4]),
            "error_message": last_log[5]
        }

    return {
        "last_sync": last_sync_info,
        "recent_logs": history,
        "status": "ok"
    }
