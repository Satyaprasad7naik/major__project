"""
Draft Purchase Order Module for InsightOS.

Purpose: Convert reorder recommendations into actionable draft POs.
New Table: purchase_orders (po_id, sku, qty, supplier_id, status, etc.)

Status flow: DRAFT → APPROVED → SENT → RECEIVED → CANCELLED
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import HTTPException
from app.modules.stockout_analyzer import analyze_stockout_risk, calculate_reorder_qty


# ────────────────────────────────────────────────────────────────────
# Purchase Order Status
# ────────────────────────────────────────────────────────────────────

PO_STATUS_CHOICES = ["DRAFT", "APPROVED", "SENT", "RECEIVED", "CANCELLED"]


def po_status_is_valid(status: str) -> bool:
    """Check if status is a valid PO status."""
    return status in PO_STATUS_CHOICES


# ────────────────────────────────────────────────────────────────────
# In-memory PO store (placeholder - would be DB in production)
# ────────────────────────────────────────────────────────────────────

# Format: {po_id: po_data}
_pos: Dict[str, Dict[str, Any]] = {}


# ────────────────────────────────────────────────────────────────────
# PO Lifecycle Helpers
# ────────────────────────────────────────────────────────────────────

def generate_po_id() -> str:
    """Generate a unique PO ID: PO-YYYYMMDD-XXXX"""
    return f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"


def po_lifecycle_transition(po_id: str, to_status: str) -> Dict[str, Any]:
    """Validate and transition PO to new status."""
    if po_id not in _pos:
        raise HTTPException(status_code=404, detail=f"PO {po_id} not found")

    if not po_status_is_valid(to_status):
        raise HTTPException(status_code=400, detail=f"Invalid status: {to_status}")

    po = _pos[po_id]
    old_status = po["status"]

    # Validate transition rules
    transition_rules = {
        "DRAFT": ["APPROVED", "CANCELLED"],
        "APPROVED": ["SENT"],
        "SENT": ["RECEIVED", "CANCELLED"],
        "RECEIVED": [],  # Terminal state
        "CANCELLED": [],  # Terminal state
    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }

    }
    }

    }

    }
    }

    }
    }

    if to_status not in transition_rules.get(old_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition PO from {old_status} to {to_status}"
        )

    po["status"] = to_status
    if to_status not in ["DRAFT"] and "transitioned_at" not in po:
        po["transitioned_at"] = datetime.utcnow().isoformat()

    _pos[po_id] = po
    return po


# ────────────────────────────────────────────────────────────────────
# Create Draft PO from Stockout Recommendation
# ────────────────────────────────────────────────────────────────────

async def create_draft_po_from_stockout(
    domain: str,
    sku: str,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a draft PO from a stockout risk analysis.

    Usage: When stockout risk is detected, show "Create Draft PO" button.
    On click: fetch the at-risk product details, calculate reorder qty,
    and create a pre-filled draft PO.
    """
    # Run stockout analysis to get product details
    results = await analyze_stockout_risk(domain, threshold_days=7, method="auto")

    # Find the matching SKU
    product = next((r for r in results if r['sku'] == sku), None)

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"SKU {sku} not found in stockout analysis for domain {domain}"
        )

    # Calculate reorder quantity
    reorder_qty = calculate_reorder_qty(
        stock_count=product['stock_count'],
        reorder_point=product['reorder_point'],
        lead_time_days=product['lead_time_days'],
        avg_daily_sales=product.get('avg_daily_sales') or 0
    )

    # Determine supplier
    supplier_id = product.get('supplier_id') or product.get('supplier_name', 'SUP-DEFAULT')
    supplier_name = product.get('supplier_name', 'Unknown Supplier')

    # Generate PO
    po_id = generate_po_id()
    total_cost = reorder_qty * product.get('unit_cost', product.get('retail_price', 0) * 0.4)

    po_data = {
        "po_id": po_id,
        "domain": domain,
        "sku": sku,
        "style_name": product.get('style_name', 'Unknown'),
        "category": product.get('category', 'Unknown'),
        "qty": reorder_qty,
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "unit_cost": product.get('unit_cost', round(product.get('retail_price', 25.0) * 0.4, 2)),
        "total_cost": round(total_cost, 2),
        "status": "DRAFT",
        "recommended_by": "auto_insight",
        "insight_id": None,  # Will be set if from specific insight
        "notes": f"Auto-generated from stockout risk analysis: {product['style_name']} ({sku}) has {product.get('days_of_cover')} days of cover",
        "created_at": datetime.utcnow().isoformat(),
        "approved_at": None,
        "approved_by": None,
    }

    _pos[po_id] = po_data
    return po_data


# ────────────────────────────────────────────────────────────────────
# Get PO by ID
# ────────────────────────────────────────────────────────────────────

def get_po(po_id: str) -> Dict[str, Any]:
    """Get a PO by its ID."""
    if po_id not in _pos:
        raise HTTPException(status_code=404, detail=f"PO {po_id} not found")
    return _pos[po_id]


# ────────────────────────────────────────────────────────────────────
# List POs with filters
# ────────────────────────────────────────────────────────────────────

def list_pos(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    sku: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List POs with optional filters."""
    results = list(_pos.values())

    if status:
        results = [po for po in results if po.get("status") == status]

    if domain:
        results = [po for po in results if po.get("domain") == domain]

    if sku:
        results = [po for po in results if po.get("sku") == sku]

    return results


# ────────────────────────────────────────────────────────────────────
# Approve PO
# ────────────────────────────────────────────────────────────────────

async def approve_po(po_id: str, approved_by: str = "system") -> Dict[str, Any]:
    """Approve a draft PO."""
    po = po_lifecycle_transition(po_id, "APPROVED")
    po["approved_by"] = approved_by
    po["approved_at"] = datetime.utcnow().isoformat()
    return po


# ────────────────────────────────────────────────────────────────────
# Cancel PO
# ────────────────────────────────────────────────────────────────────

def cancel_po(po_id: str, cancelled_by: str = "system") -> Dict[str, Any]:
    """Cancel a draft PO."""
    po = po_lifecycle_transition(po_id, "CANCELLED")
    po["cancelled_by"] = cancelled_by
    return po


# ────────────────────────────────────────────────────────────────────
# Send PO (APPROVED → SENT)
# ────────────────────────────────────────────────────────────────────

def send_po(po_id: str) -> Dict[str, Any]:
    """Send an approved PO."""
    po = po_lifecycle_transition(po_id, "SENT")
    po["sent_at"] = datetime.utcnow().isoformat()
    return po


# ────────────────────────────────────────────────────────────────────
# Receive PO (SENT → RECEIVED)
# ────────────────────────────────────────────────────────────────────

def receive_po(po_id: str, received_by: str = "system") -> Dict[str, Any]:
    """Mark a sent PO as received."""
    po = po_lifecycle_transition(po_id, "RECEIVED")
    po["received_at"] = datetime.utcnow().isoformat()
    po["received_by"] = received_by
    return po