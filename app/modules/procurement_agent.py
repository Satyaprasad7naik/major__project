"""
Autonomous Procurement Agent for InsightOS.
Implements the Multi-Agent State Machine specified in AUTO_INSIGHTS_FEATURE.md:
Trigger: StockoutRisk -> SupplierLookupAgent -> Pricing&VolumeAgent -> DraftGeneratorAgent -> Human-in-the-Loop Gate -> DispatchWorker / LogAbortAuditState.
"""

from typing import TypedDict, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import sqlite3
import os
import json
import re

from app.core.logger import logger
from app.services.auto_insights import get_db_connection
from app.services.email_notifier import send_email_insight_alert

class ProcurementState(TypedDict):
    sku_id: str
    item_name: str
    projected_shortage_units: int
    predicted_stockout_date: str
    supplier_id: Optional[str]
    supplier_email: Optional[str]
    unit_cost: Optional[float]
    recommended_order_quantity: Optional[int]
    total_estimated_cost: Optional[float]
    purchase_order_id: Optional[str]
    draft_email_subject: Optional[str]
    draft_email_body: Optional[str]
    approval_status: str  # 'PENDING_REVIEW', 'APPROVED', 'REJECTED'
    error_log: List[str]


def ensure_procurement_table(conn: sqlite3.Connection):
    """Ensure procurement_proposals table exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procurement_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT UNIQUE,
            sku_id TEXT,
            item_name TEXT,
            supplier_id TEXT,
            supplier_name TEXT,
            supplier_email TEXT,
            projected_shortage_units INTEGER,
            predicted_stockout_date TEXT,
            unit_cost REAL,
            recommended_order_quantity INTEGER,
            total_estimated_cost REAL,
            draft_email_subject TEXT,
            draft_email_body TEXT,
            approval_status TEXT DEFAULT 'PENDING_REVIEW', -- 'PENDING_REVIEW', 'APPROVED', 'REJECTED'
            decision_notes TEXT,
            decided_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


class SupplierLookupAgent:
    """Agent node that inspects vendor catalogs and maps primary supplier & email."""
    @staticmethod
    def run(state: ProcurementState, conn: sqlite3.Connection) -> ProcurementState:
        try:
            cursor = conn.cursor()
            sku = state["sku_id"]
            
            # Query product and supplier
            row = cursor.execute("""
                SELECT p.supplier_id, p.unit_cost, s.supplier_name
                FROM products p
                LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
                WHERE p.sku = ?
            """, (sku,)).fetchone()
            
            if row:
                s_name = row["supplier_name"] or "Primary Supplier"
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', s_name.lower())
                state["supplier_id"] = row["supplier_id"] or "SUP-001"
                state["supplier_email"] = f"orders@{clean_name}.com"
                if row["unit_cost"]:
                    state["unit_cost"] = float(row["unit_cost"])
            else:
                state["supplier_id"] = "SUP-001"
                state["supplier_email"] = "procurement@primary-supplier.com"
                state["unit_cost"] = state.get("unit_cost") or 35.0
        except Exception as e:
            state["error_log"].append(f"SupplierLookupAgent error: {e}")
            logger.error(f"[SupplierLookupAgent] Error for {state['sku_id']}: {e}")
        return state


class PricingAndVolumeAgent:
    """Agent node that computes economic reorder quantity (EOQ) and total cost."""
    @staticmethod
    def run(state: ProcurementState, conn: sqlite3.Connection) -> ProcurementState:
        try:
            shortage = state.get("projected_shortage_units", 0)
            # Safe reorder formula: shortage + safety buffer (min 15 units)
            rec_qty = max(shortage * 2, 15)
            state["recommended_order_quantity"] = rec_qty
            
            unit_cost = state.get("unit_cost") or 30.0
            # Tiered discount: 5% off if ordering >= 30 units
            if rec_qty >= 30:
                unit_cost = round(unit_cost * 0.95, 2)
            state["unit_cost"] = unit_cost
            state["total_estimated_cost"] = round(rec_qty * unit_cost, 2)
        except Exception as e:
            state["error_log"].append(f"PricingAndVolumeAgent error: {e}")
            logger.error(f"[PricingAndVolumeAgent] Error: {e}")
        return state


class DraftGeneratorAgent:
    """Agent node that generates structured PO identifier and draft email."""
    @staticmethod
    def run(state: ProcurementState, conn: sqlite3.Connection) -> ProcurementState:
        try:
            today_str = datetime.now().strftime("%Y%m%d")
            seq = int(datetime.now().strftime("%H%M%S")) % 1000
            po_id = f"PO-{today_str}-{seq:03d}"
            state["purchase_order_id"] = po_id
            
            item = state["item_name"]
            qty = state["recommended_order_quantity"]
            cost = state["total_estimated_cost"]
            unit_c = state["unit_cost"]
            
            state["draft_email_subject"] = f"Purchase Order Requisition: {po_id} - {item}"
            state["draft_email_body"] = (
                f"Dear Supplier Team,\n\n"
                f"Please find our purchase requisition details below:\n"
                f"Purchase Order ID: {po_id}\n"
                f"Item SKU: {state['sku_id']} ({item})\n"
                f"Quantity: {qty} units\n"
                f"Agreed Unit Cost: ${unit_c:.2f}\n"
                f"Total Estimated Value: ${cost:.2f}\n\n"
                f"Please confirm receipt and expected delivery date.\n\n"
                f"Best regards,\n"
                f"InsightOS Autonomous Procurement Engine"
            )
            state["approval_status"] = "PENDING_REVIEW"
        except Exception as e:
            state["error_log"].append(f"DraftGeneratorAgent error: {e}")
            logger.error(f"[DraftGeneratorAgent] Error: {e}")
        return state


class ProcurementStateGraph:
    """Executes the state machine graph from trigger to draft proposal."""
    @classmethod
    def execute_for_sku(cls, sku_id: str, item_name: str, shortage_units: int, db_path: str = "retail_clothing.db") -> ProcurementState:
        conn = get_db_connection(db_path)
        ensure_procurement_table(conn)
        
        initial_state: ProcurementState = {
            "sku_id": sku_id,
            "item_name": item_name,
            "projected_shortage_units": shortage_units,
            "predicted_stockout_date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
            "supplier_id": None,
            "supplier_email": None,
            "unit_cost": None,
            "recommended_order_quantity": None,
            "total_estimated_cost": None,
            "purchase_order_id": None,
            "draft_email_subject": None,
            "draft_email_body": None,
            "approval_status": "PENDING_REVIEW",
            "error_log": []
        }
        
        # State machine flow
        s1 = SupplierLookupAgent.run(initial_state, conn)
        s2 = PricingAndVolumeAgent.run(s1, conn)
        s3 = DraftGeneratorAgent.run(s2, conn)
        
        # Checkpoint proposal in database
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO procurement_proposals (
                    po_id, sku_id, item_name, supplier_id, supplier_email,
                    projected_shortage_units, predicted_stockout_date, unit_cost,
                    recommended_order_quantity, total_estimated_cost,
                    draft_email_subject, draft_email_body, approval_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                s3["purchase_order_id"], s3["sku_id"], s3["item_name"], s3["supplier_id"],
                s3["supplier_email"], s3["projected_shortage_units"], s3["predicted_stockout_date"],
                s3["unit_cost"], s3["recommended_order_quantity"], s3["total_estimated_cost"],
                s3["draft_email_subject"], s3["draft_email_body"], s3["approval_status"]
            ))
            conn.commit()
            logger.info(f"[ProcurementGraph] Generated draft proposal {s3['purchase_order_id']} for {sku_id}")
        except Exception as e:
            logger.error(f"[ProcurementGraph] Failed to persist proposal: {e}")
            s3["error_log"].append(f"Persistence error: {e}")
        finally:
            conn.close()
            
        return s3
