"""Insights API Endpoints for InsightOS."""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import sqlite3
import os
from app.modules.stockout_analyzer import analyze_stockout_risk
from app.services.auto_insights import generate_insights, get_db_connection
from app.core.logger import logger

router = APIRouter(prefix="/insights", tags=["insights"])


def _extract_str(val: Any, default_val: str) -> str:
    """Extract string value from FastAPI Query/Path parameter or default."""
    if isinstance(val, str):
        return val
    if hasattr(val, "default") and isinstance(val.default, str):
        return val.default
    return default_val


@router.post("/generate", response_model=dict)
async def trigger_insights_generation(
    domain: str = Query("retail_clothing", description="Domain to analyze"),
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """
    Directly trigger auto-insights generation and proactive email/Slack notifications.
    """
    clean_domain = _extract_str(domain, "retail_clothing")
    clean_db_path = _extract_str(db_path, "retail_clothing.db")

    logger.info(f"Direct insights generation requested for domain: {clean_domain}, db_path: {clean_db_path}")

    try:
        insights = generate_insights(clean_db_path)
        headline = f"{len(insights)} products need urgent attention today" if insights else "No urgent stock alerts"
        return {
            "status": "success",
            "message": "Auto insights generated successfully",
            "summary_headline": headline,
            "count": len(insights),
            "insights": insights
        }
    except Exception as exc:
        logger.error(f"Insights generation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/today", response_model=dict)
async def get_today_insights(
    domain: str = Query("retail_clothing", description="Domain to analyze"),
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """Return today's auto-generated insights ordered by severity."""
    clean_domain = _extract_str(domain, "retail_clothing")
    clean_db_path = _extract_str(db_path, "retail_clothing.db")

    logger.info(f"Today insights request for domain: {clean_domain}, db_path: {clean_db_path}")

    # Trigger generation to ensure up-to-date insights exist
    try:
        generate_insights(clean_db_path)
    except Exception as e:
        logger.warning(f"On-demand insights generation warning: {e}")

    conn = None
    try:
        conn = get_db_connection(clean_db_path)
        cursor = conn.cursor()

        # Check table info to build safe column selection
        pragma = cursor.execute("PRAGMA table_info(auto_insights)").fetchall()
        cols = {p[1] for p in pragma}

        id_expr = "id" if "id" in cols else "rowid AS id"
        prod_id_expr = "product_id" if "product_id" in cols else ("sku AS product_id" if "sku" in cols else "rowid AS product_id")
        prod_name_expr = "product_name" if "product_name" in cols else "title AS product_name"
        is_read_expr = "is_read" if "is_read" in cols else "0 AS is_read"

        rec_action_expr = "recommended_action" if "recommended_action" in cols else "NULL AS recommended_action"
        reorder_qty_expr = "suggested_reorder_qty" if "suggested_reorder_qty" in cols else "NULL AS suggested_reorder_qty"
        payload_expr = "payload_json" if "payload_json" in cols else "NULL AS payload_json"

        query = f"""
            SELECT 
                {id_expr},
                insight_id,
                insight_type,
                title,
                description,
                severity,
                {prod_id_expr},
                {prod_name_expr},
                created_at,
                {is_read_expr},
                {rec_action_expr},
                {reorder_qty_expr},
                {payload_expr}
            FROM auto_insights
            WHERE date(created_at) = date('now')
               OR created_at >= date('now', '-1 day')
            ORDER BY
                CASE LOWER(severity)
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                created_at DESC
            LIMIT 20
        """

        rows = cursor.execute(query).fetchall()

        insights_list = []
        for r in rows:
            payload_dict = {}
            if r["payload_json"]:
                try:
                    payload_dict = json.loads(r["payload_json"])
                except Exception:
                    payload_dict = {}

            rec_act = r["recommended_action"] or payload_dict.get("recommended_action")
            reorder_qty = r["suggested_reorder_qty"] if r["suggested_reorder_qty"] is not None else payload_dict.get("suggested_reorder_qty")

            if not rec_act:
                if (r["severity"] or "").lower() in ("critical", "high"):
                    rec_act = f"Reorder 15 units immediately"
                elif r["insight_type"] == "sales_drop":
                    rec_act = f"Review promotional discount strategy"

            insights_list.append({
                "id": r["id"],
                "insight_id": r["insight_id"],
                "type": r["insight_type"],
                "insight_type": r["insight_type"],
                "title": r["title"],
                "description": r["description"],
                "severity": (r["severity"] or "medium").lower(),
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "recommended_action": rec_act,
                "suggested_reorder_qty": reorder_qty if reorder_qty is not None else (15 if (r["severity"] or "").lower() in ("critical", "high") else 0),
                "created_at": str(r["created_at"]),
                "is_read": bool(r["is_read"])
            })

        urgent_products = {r["product_id"] for r in insights_list if (r.get("severity") or "").lower() in ("high", "critical") and r["product_id"]}
        urgent_count = len(urgent_products) if urgent_products else len([r for r in insights_list if (r.get("severity") or "").lower() in ("high", "critical")])
        if urgent_count > 0:
            summary_headline = f"{urgent_count} products need urgent attention today"
        else:
            summary_headline = "All systems normal: inventory & sales performing smoothly"

        return {
            "summary_headline": summary_headline,
            "urgent_count": urgent_count,
            "insights": insights_list,
            "count": len(insights_list),
            "domain": clean_domain,
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as exc:
        logger.error(f"Failed to fetch today insights: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.patch("/{insight_id}/read", response_model=dict)
@router.patch("/read/{insight_id}", response_model=dict)
async def mark_insight_as_read(
    insight_id: str = Path(..., description="ID or insight_id of the insight to mark as read"),
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """Mark a single insight as read."""
    clean_insight_id = _extract_str(insight_id, "")
    clean_db_path = _extract_str(db_path, "retail_clothing.db")

    logger.info(f"Marking insight as read: {clean_insight_id}")
    conn = None
    try:
        conn = get_db_connection(clean_db_path)
        cursor = conn.cursor()

        pragma = cursor.execute("PRAGMA table_info(auto_insights)").fetchall()
        cols = {p[1] for p in pragma}

        if "id" in cols:
            id_clause = "id = ? OR insight_id = ? OR rowid = ?"
            params = (clean_insight_id, clean_insight_id, clean_insight_id)
        else:
            id_clause = "insight_id = ? OR rowid = ?"
            params = (clean_insight_id, clean_insight_id)

        cursor.execute(f"""
            UPDATE auto_insights
            SET is_read = 1,
                status = 'ACKNOWLEDGED',
                acknowledged_at = CURRENT_TIMESTAMP
            WHERE {id_clause}
        """, params)

        conn.commit()
        return {"status": "ok", "insight_id": clean_insight_id, "is_read": True}
    except Exception as exc:
        logger.error(f"Failed to mark insight as read: {exc}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.get("/risk", response_model=dict)
async def get_insights_risk(
    domain: str = Query("retail_clothing", description="Domain to analyze"),
    method: str = Query("auto", description="Calculation method: simple, days_of_cover, auto"),
):
    """Get insights risk analysis."""
    clean_domain = _extract_str(domain, "retail_clothing")
    clean_method = _extract_str(method, "auto")

    logger.info(f"Insights risk request for domain: {clean_domain}, method: {clean_method}")
    try:
        results = analyze_stockout_risk(clean_domain, method=clean_method)
        return {
            "domain": clean_domain,
            "method": clean_method,
            "count": len(results),
            "at_risk_products": results,
            "status": "ok"
        }
    except Exception as e:
        logger.error(f"Insights risk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EmailConfigPayload(BaseModel):
    sender_email: Optional[str] = None
    sender_password: Optional[str] = None
    receiver_emails: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None


@router.get("/email/status", response_model=dict)
@router.get("/email/config", response_model=dict)
async def get_email_notification_status():
    """Get email notification configuration diagnostics."""
    from app.services.email_notifier import get_smtp_status
    return get_smtp_status()


@router.post("/email/config", response_model=dict)
async def configure_email_notifications(payload: EmailConfigPayload):
    """Save sender and receiver email configuration to backend runtime and .env file."""
    from app.services.email_notifier import update_email_config
    return update_email_config(
        sender_email=payload.sender_email,
        sender_password=payload.sender_password,
        receiver_emails=payload.receiver_emails,
        smtp_server=payload.smtp_server,
        smtp_port=payload.smtp_port,
    )


@router.post("/email/test", response_model=dict)
async def test_email_notification(
    payload: Optional[EmailConfigPayload] = None,
    recipient: Optional[str] = Query(None, description="Optional override recipient email")
):
    """Trigger a test email notification with runtime credentials or saved config."""
    from app.services.email_notifier import test_email_connection
    sender_email = payload.sender_email if payload else None
    sender_password = payload.sender_password if payload else None
    receiver_emails = (payload.receiver_emails if payload and payload.receiver_emails else recipient)
    smtp_server = payload.smtp_server if payload else None
    smtp_port = payload.smtp_port if payload else None

    return await test_email_connection(
        sender_email=sender_email,
        sender_password=sender_password,
        receiver_emails=receiver_emails,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        save_config=True
    )


