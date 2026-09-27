"""
Purchase Orders API Endpoints for InsightOS.
Supports creating, retrieving, and updating Draft Purchase Orders generated from Auto Insights.
"""

from fastapi import APIRouter, HTTPException, Query, Path, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import sqlite3
import os
from app.services.auto_insights import get_db_connection
from app.core.logger import logger

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


def _clean_str(val: Any, default: str) -> str:
    if isinstance(val, str):
        return val.strip()
    if hasattr(val, "default") and isinstance(val.default, str):
        return val.default.strip()
    return default


def _generate_po_number(conn: sqlite3.Connection) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"PO-{today_str}-"

    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT po_number FROM purchase_orders 
        WHERE po_number LIKE ? 
        ORDER BY id DESC LIMIT 10
    """, (f"{prefix}%",)).fetchall()

    max_seq = 0
    for r in rows:
        po_num = r["po_number"] if r and "po_number" in r.keys() else ""
        if po_num and po_num.startswith(prefix):
            try:
                seq = int(po_num.replace(prefix, ""))
                if seq > max_seq:
                    max_seq = seq
            except ValueError:
                pass

    return f"{prefix}{max_seq + 1:03d}"


class DraftPOCreate(BaseModel):
    product_id: Optional[str] = Field("SKU-UNKNOWN", description="SKU or product ID")
    product_name: Optional[str] = Field(None, description="Product name")
    quantity: Optional[int] = Field(15, description="Order quantity")
    supplier_id: Optional[str] = Field(None, description="Supplier ID")
    supplier_name: Optional[str] = Field(None, description="Supplier Name")
    notes: Optional[str] = Field("Created from Auto Insight", description="Notes")
    db_path: Optional[str] = Field("retail_clothing.db", description="Target database file")


class POUpdate(BaseModel):
    status: Optional[str] = Field(None, description="Draft / Approved / Ordered / Cancelled")
    quantity: Optional[int] = Field(None, description="Updated quantity")
    notes: Optional[str] = Field(None, description="Updated notes")
    db_path: Optional[str] = Field("retail_clothing.db", description="Target database file")


def _ensure_po_schema(conn: sqlite3.Connection):
    """Ensure purchase_orders table exists with all required columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT UNIQUE,
            product_id TEXT,
            product_name TEXT,
            quantity INTEGER,
            supplier_id TEXT,
            supplier_name TEXT,
            status TEXT DEFAULT 'Draft',
            unit_cost REAL,
            total_cost REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        );
    """)
    conn.commit()


@router.post("/draft", response_model=dict)
@router.post("", response_model=dict)
async def create_draft_po(payload: Optional[DraftPOCreate] = Body(None)):
    """Create a new Draft Purchase Order from an insight or action."""
    if payload is None:
        payload = DraftPOCreate()
    clean_db = payload.db_path or "retail_clothing.db"
    conn = None

    try:
        conn = get_db_connection(clean_db)
        _ensure_po_schema(conn)
        cursor = conn.cursor()

        p_id = payload.product_id.strip()
        p_name = payload.product_name.strip() if payload.product_name else ""
        qty = payload.quantity
        sup_id = payload.supplier_id.strip() if payload.supplier_id else ""
        sup_name = payload.supplier_name.strip() if payload.supplier_name else ""
        notes = payload.notes or "Created from Auto Insight"

        unit_cost = 0.0
        # Lookup product details if missing
        pragma_p = cursor.execute("PRAGMA table_info(products)").fetchall()
        p_cols = {row[1] for row in pragma_p}

        if p_cols:
            id_col = "product_id" if "product_id" in p_cols else "sku"
            name_col = "name" if "name" in p_cols else ("style_name" if "style_name" in p_cols else id_col)

            prod = cursor.execute(f"SELECT * FROM products WHERE {id_col} = ? OR sku = ?", (p_id, p_id)).fetchone()
            if prod:
                if not p_name and name_col in prod.keys() and prod[name_col]:
                    p_name = str(prod[name_col])
                if "unit_cost" in prod.keys() and prod["unit_cost"] is not None:
                    unit_cost = float(prod["unit_cost"])
                if not sup_id and "supplier_id" in prod.keys() and prod["supplier_id"]:
                    sup_id = str(prod["supplier_id"])

        if not p_name:
            p_name = f"Product {p_id}"

        # Lookup supplier name if missing
        if sup_id and not sup_name:
            pragma_sup = cursor.execute("PRAGMA table_info(suppliers)").fetchall()
            sup_cols = {row[1] for row in pragma_sup}
            if sup_cols and "supplier_name" in sup_cols:
                sup_row = cursor.execute("SELECT supplier_name FROM suppliers WHERE supplier_id = ?", (sup_id,)).fetchone()
                if sup_row and sup_row["supplier_name"]:
                    sup_name = str(sup_row["supplier_name"])

        if not sup_id:
            sup_id = "SUP-001"
        if not sup_name:
            sup_name = "Primary Supplier"
        if unit_cost <= 0:
            unit_cost = 25.0

        total_cost = round(unit_cost * qty, 2)
        po_num = _generate_po_number(conn)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check existing table columns in purchase_orders
        pragma_po = cursor.execute("PRAGMA table_info(purchase_orders)").fetchall()
        po_cols = {row[1] for row in pragma_po}

        fields = {
            "po_number": po_num,
            "product_id": p_id,
            "product_name": p_name,
            "quantity": qty,
            "supplier_id": sup_id,
            "supplier_name": sup_name,
            "status": "Draft",
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "notes": notes,
            "created_at": now_str,
            "updated_at": now_str
        }

        # Handle backward compatibility with older schemas (po_id, sku, qty)
        if "po_id" in po_cols: fields["po_id"] = po_num
        if "sku" in po_cols: fields["sku"] = p_id
        if "qty" in po_cols: fields["qty"] = qty

        valid_fields = {k: v for k, v in fields.items() if k in po_cols}

        cols_str = ", ".join(valid_fields.keys())
        placeholders = ", ".join(["?"] * len(valid_fields))
        values = list(valid_fields.values())

        cursor.execute(f"INSERT INTO purchase_orders ({cols_str}) VALUES ({placeholders})", values)
        new_id = cursor.lastrowid
        conn.commit()

        logger.info(f"[Purchase Orders] Created Draft Purchase Order {po_num} (ID: {new_id}) for {p_name} ({qty} units)")

        po_data = {
            "id": new_id,
            "po_number": po_num,
            "product_id": p_id,
            "product_name": p_name,
            "quantity": qty,
            "supplier_id": sup_id,
            "supplier_name": sup_name,
            "status": "Draft",
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "notes": notes,
            "created_at": now_str
        }

        return {
            "status": "success",
            "message": "Draft Purchase Order created",
            "po_number": po_num,
            "data": po_data
        }

    except Exception as exc:
        logger.error(f"Error creating Draft PO: {exc}")
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create draft purchase order: {str(exc)}")
    finally:
        if conn: conn.close()


@router.get("", response_model=dict)
@router.get("/list", response_model=dict)
async def get_purchase_orders(
    status: Optional[str] = Query("Draft", description="Filter by status (Draft, Approved, Ordered, Cancelled, All)"),
    db_path: str = Query("retail_clothing.db", description="Database file path")
):
    """List purchase orders matching status filter."""
    clean_db = _clean_str(db_path, "retail_clothing.db")
    conn = None

    try:
        conn = get_db_connection(clean_db)
        _ensure_po_schema(conn)
        cursor = conn.cursor()

        pragma_po = cursor.execute("PRAGMA table_info(purchase_orders)").fetchall()
        po_cols = {row[1] for row in pragma_po}

        id_expr = "rowid AS id"
        po_num_expr = "po_number" if "po_number" in po_cols else "po_id AS po_number"
        prod_id_expr = "product_id" if "product_id" in po_cols else "sku AS product_id"
        prod_name_expr = "product_name" if "product_name" in po_cols else "product_id AS product_name"
        qty_expr = "quantity" if "quantity" in po_cols else "qty AS quantity"
        sup_name_expr = "supplier_name" if "supplier_name" in po_cols else "supplier_id AS supplier_name"

        base_query = f"""
            SELECT 
                {id_expr},
                {po_num_expr},
                {prod_id_expr},
                {prod_name_expr},
                {qty_expr},
                supplier_id,
                {sup_name_expr},
                status,
                unit_cost,
                total_cost,
                notes,
                created_at
            FROM purchase_orders
        """

        if status and status.lower() != "all":
            query = f"{base_query} WHERE LOWER(status) = LOWER(?) ORDER BY rowid DESC"
            rows = cursor.execute(query, (status,)).fetchall()
        else:
            query = f"{base_query} ORDER BY rowid DESC"
            rows = cursor.execute(query).fetchall()

        orders = []
        for r in rows:
            orders.append({
                "id": r["id"],
                "po_number": r["po_number"] or f"PO-{r['id']:04d}",
                "product_id": r["product_id"],
                "product_name": r["product_name"] or r["product_id"],
                "quantity": r["quantity"] or 0,
                "supplier_id": r["supplier_id"],
                "supplier_name": r["supplier_name"] or r["supplier_id"],
                "status": r["status"] or "Draft",
                "unit_cost": r["unit_cost"] or 0.0,
                "total_cost": r["total_cost"] or 0.0,
                "notes": r["notes"] or "",
                "created_at": str(r["created_at"]) if r["created_at"] else ""
            })

        return {
            "status": "success",
            "count": len(orders),
            "purchase_orders": orders
        }

    except Exception as exc:
        logger.error(f"Error fetching purchase orders: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch purchase orders: {str(exc)}")
    finally:
        if conn: conn.close()


@router.patch("/{po_id}", response_model=dict)
async def update_purchase_order_status(
    po_id: str = Path(..., description="ID or PO Number of purchase order"),
    payload: Optional[POUpdate] = Body(None)
):
    """Update status, quantity, or notes of a Purchase Order."""
    if payload is None:
        payload = POUpdate()
    clean_db = payload.db_path or "retail_clothing.db"
    conn = None

    try:
        conn = get_db_connection(clean_db)
        _ensure_po_schema(conn)
        cursor = conn.cursor()

        pragma_po = cursor.execute("PRAGMA table_info(purchase_orders)").fetchall()
        po_cols = {row[1] for row in pragma_po}

        try:
            int_id = int(po_id)
        except ValueError:
            int_id = -1

        existing = cursor.execute("""
            SELECT rowid AS id, * FROM purchase_orders 
            WHERE rowid = ? OR po_number = ? OR (id IS NOT NULL AND id = ?)
        """, (int_id, po_id, int_id)).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail=f"Purchase order '{po_id}' not found")

        updates = []
        params = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if payload.status:
            updates.append("status = ?")
            params.append(payload.status.strip())

        if payload.notes is not None:
            updates.append("notes = ?")
            params.append(payload.notes.strip())

        if payload.quantity is not None and payload.quantity > 0:
            qty = payload.quantity
            if "quantity" in po_cols:
                updates.append("quantity = ?")
                params.append(qty)
            if "qty" in po_cols:
                updates.append("qty = ?")
                params.append(qty)

            unit_cost = float(existing["unit_cost"] or 0.0)
            if unit_cost > 0:
                new_total = round(unit_cost * qty, 2)
                updates.append("total_cost = ?")
                params.append(new_total)

        if "updated_at" in po_cols:
            updates.append("updated_at = ?")
            params.append(now_str)

        if not updates:
            return {"status": "success", "message": "No changes requested"}

        params.append(existing["id"])
        sql = f"UPDATE purchase_orders SET {', '.join(updates)} WHERE rowid = ?"
        cursor.execute(sql, params)
        conn.commit()

        logger.info(f"[Purchase Orders] Updated Purchase Order '{po_id}' -> status: {payload.status or existing['status']}")

        return {
            "status": "success",
            "message": f"Purchase order '{po_id}' updated successfully"
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error updating purchase order {po_id}: {exc}")
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update purchase order: {str(exc)}")
    finally:
        if conn: conn.close()
