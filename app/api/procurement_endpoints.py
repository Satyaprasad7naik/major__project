"""
Procurement API Endpoints for InsightOS.
Endpoints specified in AUTO_INSIGHTS_FEATURE.md:
- POST /api/v1/procurement/trigger
- GET /api/v1/procurement/proposals/pending
- POST /api/v1/procurement/proposals/{po_id}/decision
"""

from fastapi import APIRouter, HTTPException, Query, Path, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import sqlite3

from app.modules.procurement_agent import ProcurementStateGraph, ensure_procurement_table
from app.services.auto_insights import get_db_connection
from app.services.email_notifier import send_email_insight_alert
from app.core.logger import logger

router = APIRouter(prefix="/procurement", tags=["procurement"])


class TriggerRequest(BaseModel):
    domain: Optional[str] = Field("retail_clothing", description="Domain to analyze")
    db_path: Optional[str] = Field("retail_clothing.db", description="Target database file")
    threshold_days: Optional[int] = Field(7, description="Stockout threshold days")


class DecisionRequest(BaseModel):
    action: str = Field(..., example="APPROVE", description="'APPROVE' or 'REJECT'")
    notes: Optional[str] = Field(None, description="Optional manager approval notes")
    db_path: Optional[str] = Field("retail_clothing.db", description="Database file path")


@router.post("/trigger", response_model=dict)
async def trigger_procurement(payload: Optional[TriggerRequest] = Body(None)):
    """
    Evaluates low-stock thresholds across inventory and starts the autonomous procurement agent run.
    """
    clean_db = "retail_clothing.db"
    if payload and hasattr(payload, "db_path") and payload.db_path:
        clean_db = payload.db_path
    conn = None
    try:
        conn = get_db_connection(clean_db)
        ensure_procurement_table(conn)
        cursor = conn.cursor()
        
        # Look for items at or below reorder point
        rows = cursor.execute("""
            SELECT i.sku, i.stock_count, i.reorder_point, p.style_name
            FROM inventory i
            LEFT JOIN products p ON i.sku = p.sku
            WHERE i.stock_count <= i.reorder_point
            LIMIT 10
        """).fetchall()
        
        generated_proposals = []
        for r in rows:
            sku = r["sku"]
            stock = r["stock_count"] or 0
            reorder = r["reorder_point"] or 10
            name = r["style_name"] or f"Product {sku}"
            shortage = max(reorder - stock, 5)
            
            # Execute multi-agent state graph for each shortage item
            state = ProcurementStateGraph.execute_for_sku(
                sku_id=sku,
                item_name=name,
                shortage_units=shortage,
                db_path=clean_db
            )
            generated_proposals.append(state)
            
        return {
            "status": "success",
            "message": f"Autonomous procurement run completed. Generated {len(generated_proposals)} draft PO proposals.",
            "count": len(generated_proposals),
            "proposals": generated_proposals
        }
    except Exception as exc:
        logger.error(f"Procurement trigger failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.get("/proposals/pending", response_model=dict)
async def get_pending_proposals(
    db_path: str = Query("retail_clothing.db", description="Database file path")
):
    """
    Returns pending PO drafts awaiting one-click human confirmation.
    """
    clean_db = db_path if isinstance(db_path, str) else "retail_clothing.db"
    conn = None
    try:
        conn = get_db_connection(clean_db)
        ensure_procurement_table(conn)
        cursor = conn.cursor()
        
        rows = cursor.execute("""
            SELECT * FROM procurement_proposals
            WHERE approval_status = 'PENDING_REVIEW'
            ORDER BY id DESC
        """).fetchall()
        
        proposals = [dict(r) for r in rows]
        return {
            "status": "success",
            "count": len(proposals),
            "pending_proposals": proposals
        }
    except Exception as exc:
        logger.error(f"Fetch pending proposals failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.post("/proposals/{po_id}/decision", response_model=dict)
async def process_po_decision(
    po_id: str = Path(..., description="Purchase Order ID (e.g., PO-20260903-001)"),
    payload: DecisionRequest = Body(...)
):
    """
    Human-in-the-Loop Decision Gate:
    Accepts action 'APPROVE' or 'REJECT'. If approved, transitions proposal to 'APPROVED' / 'ORDERED'
    and dispatches supplier notification. If rejected, transitions to 'REJECTED'.
    """
    clean_action = payload.action.strip().upper()
    if clean_action not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="Action must be 'APPROVE' or 'REJECT'")
        
    clean_db = payload.db_path or "retail_clothing.db"
    conn = None
    try:
        conn = get_db_connection(clean_db)
        ensure_procurement_table(conn)
        cursor = conn.cursor()
        
        row = cursor.execute(
            "SELECT * FROM procurement_proposals WHERE po_id = ? OR id = ?",
            (po_id, po_id)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Proposal '{po_id}' not found")
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_status = "APPROVED" if clean_action == "APPROVE" else "REJECTED"
        
        cursor.execute("""
            UPDATE procurement_proposals
            SET approval_status = ?, decision_notes = ?, decided_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, payload.notes, now_str, row["id"]))
        
        # If approved, also sync into purchase_orders table
        if clean_action == "APPROVE":
            cursor.execute("""
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
            cursor.execute("""
                INSERT OR REPLACE INTO purchase_orders (
                    po_id, po_number, sku, qty, product_id, product_name, quantity, supplier_id,
                    supplier_name, status, unit_cost, total_cost, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Approved', ?, ?, ?, ?)
            """, (
                row["po_id"], row["po_id"], row["sku_id"], row["recommended_order_quantity"],
                row["sku_id"], row["item_name"], row["recommended_order_quantity"],
                row["supplier_id"], row["supplier_name"] or "Primary Supplier",
                row["unit_cost"], row["total_estimated_cost"], payload.notes or "Approved via Human-in-the-Loop Gate",
                now_str
            ))
            
            # Dispatch supplier alert notification
            try:
                alert_insight = [{
                    "title": f"Procurement Order Approved: {row['po_id']}",
                    "severity": "CRITICAL",
                    "description": f"Approved order of {row['recommended_order_quantity']} units of {row['item_name']} (${row['total_estimated_cost']:.2f}).",
                    "product_name": row["item_name"]
                }]
                await send_email_insight_alert(alert_insight, f"Purchase Order {row['po_id']} Approved")
            except Exception as mail_err:
                logger.warning(f"Supplier email dispatch warning: {mail_err}")
                
        conn.commit()
        logger.info(f"[ProcurementDecision] PO {row['po_id']} decision: {new_status}")
        
        return {
            "status": "success",
            "po_id": row["po_id"],
            "decision": new_status,
            "message": f"Proposal {row['po_id']} has been {new_status.lower()}.",
            "decided_at": now_str
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Decision processing failed: {exc}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()
