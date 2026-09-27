"""
Auto Insights Generation Service for InsightOS (Proactive Insights Engine).
Analyzes inventory stock levels and sales trends to proactively generate
insights and save them in the auto_insights table.
Triggers proactive Slack & Email notifications for high-priority signals.
"""

from datetime import datetime
import json
import sqlite3
import os
import asyncio
from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.services.slack_notifier import notify_slack
from app.services.email_notifier import send_email_insight_alert


def get_db_connection(db_path: str = "retail_clothing.db") -> sqlite3.Connection:
    """Helper to get a SQLite connection with Row factory."""
    if not os.path.isabs(db_path):
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(project_dir, db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _dispatch_notifications_sync(new_insights: List[Dict[str, Any]], headline: str):
    """Safely dispatch async Slack & Email notifications from synchronous workflow."""
    if not new_insights:
        return

    high_critical = [i for i in new_insights if (i.get("severity") or "").lower() in ("high", "critical")]
    if not high_critical:
        return

    async def _send():
        # Dispatch email
        await send_email_insight_alert(high_critical, headline)
        # Dispatch slack
        for ins in high_critical:
            detection_payload = {
                "mission_name": ins.get("title", "Proactive Insight"),
                "severity": ins.get("severity", "HIGH").upper(),
                "domain": "inventory",
                "risk_score": 85 if (ins.get("severity") or "").lower() == "critical" else 70,
                "data_count": 1,
                "insight": ins.get("description", ""),
                "recommendation": f"Review product: {ins.get('product_name', ins.get('product_id'))}",
            }
            await notify_slack(detection_payload)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send())
    except RuntimeError:
        asyncio.run(_send())


def calculate_reorder_qty(current_stock: int, reorder_point: int) -> int:
    """
    Calculate suggested reorder quantity based on current stock and reorder point.
    Formula:
      - If stock <= 0: max(reorder_point * 3, 15)
      - If stock < reorder_point: (reorder_point - current_stock) + reorder_point
      - Else: reorder_point
    """
    try:
        stock = int(current_stock or 0)
        reorder = int(reorder_point or 5)
    except (ValueError, TypeError):
        stock, reorder = 0, 5

    if stock <= 0:
        return max(reorder * 3, 15)
    elif stock < reorder:
        return (reorder - stock) + reorder
    else:
        return reorder


def generate_insights(db_path: str = "retail_clothing.db") -> List[Dict[str, Any]]:
    """
    Generate and store auto insights based on current inventory & sales data.
    Fixed Queries:
      1. Products with days of cover < 3
      2. Products with sudden sales drop (>= 30%)
      3. High-risk items (stock <= reorder point or 0 stock)
    """
    logger.info(f"Generating auto insights for database: {db_path}")
    conn = None
    insights: List[Dict[str, Any]] = []

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Check existing table structure in database
        pragma = cursor.execute("PRAGMA table_info(products)").fetchall()
        prod_cols = [p[1] for p in pragma]

        id_col = "product_id" if "product_id" in prod_cols else "sku"
        name_col = "name" if "name" in prod_cols else ("style_name" if "style_name" in prod_cols else "sku")

        pragma_inv = cursor.execute("PRAGMA table_info(inventory)").fetchall()
        inv_cols = [i[1] for i in pragma_inv]
        stock_col = "current_stock" if "current_stock" in inv_cols else "stock_count"
        reorder_col = "reorder_point" if "reorder_point" in inv_cols else "5"

        pragma_sales = cursor.execute("PRAGMA table_info(sales_events)").fetchall()
        sales_cols = [s[1] for s in pragma_sales]
        sales_table = "sales_events" if sales_cols else "sales"

        if sales_cols:
            qty_col = "quantity" if "quantity" in sales_cols else "units_sold"
        else:
            pragma_s = cursor.execute("PRAGMA table_info(sales)").fetchall()
            s_cols = [s[1] for s in pragma_s]
            qty_col = "quantity" if "quantity" in s_cols else "units_sold"

        # Determine reference date (max date in sales table or current date)
        ref_date_expr = f"COALESCE((SELECT MAX(sale_date) FROM {sales_table}), date('now'))"

        seen_products = set()

        # -------------------------------------------------
        # Rule 1: Products with low days of cover (< 3 days)
        # -------------------------------------------------
        reorder_select = f"i.{reorder_col}" if "reorder_point" in inv_cols else "5 AS reorder_point"
        stockout_query = f"""
            SELECT 
                p.{id_col} AS prod_id,
                p.{name_col} AS prod_name,
                i.{stock_col} AS current_stock,
                {reorder_select},
                ROUND(i.{stock_col} * 1.0 / NULLIF(s.avg_daily_sales, 0), 1) AS days_cover
            FROM products p
            JOIN inventory i ON p.{id_col} = i.{id_col}
            JOIN (
                SELECT 
                    {id_col}, 
                    AVG({qty_col}) AS avg_daily_sales
                FROM {sales_table}
                WHERE sale_date >= date({ref_date_expr}, '-14 days')
                GROUP BY {id_col}
            ) s ON p.{id_col} = s.{id_col}
            WHERE ROUND(i.{stock_col} * 1.0 / NULLIF(s.avg_daily_sales, 0), 1) < 3
            ORDER BY days_cover ASC
            LIMIT 10
        """

        try:
            results = cursor.execute(stockout_query).fetchall()
            for row in results:
                days = row["days_cover"]
                prod_name = row["prod_name"]
                prod_id = row["prod_id"]
                current_stock = int(row["current_stock"] or 0)
                reorder_pt = int(row["reorder_point"] or 5)

                seen_products.add(str(prod_id))
                reorder_qty = calculate_reorder_qty(current_stock, reorder_pt)
                rec_action = f"Reorder {reorder_qty} units immediately"

                if current_stock <= 0:
                    title = f"{prod_name} is out of stock"
                    desc = f"Current stock is 0 units (Reorder point: {reorder_pt} units)."
                    severity = "critical"
                else:
                    title = f"{prod_name} is running low"
                    desc = f"Only {days} days of stock left. Current stock: {current_stock} units (Reorder point: {reorder_pt} units)."
                    severity = "high" if days < 2 else "medium"

                insights.append({
                    "insight_type": "stockout",
                    "title": title,
                    "description": desc,
                    "severity": severity,
                    "product_id": str(prod_id),
                    "product_name": str(prod_name),
                    "sku": str(prod_id),
                    "recommended_action": rec_action,
                    "suggested_reorder_qty": reorder_qty
                })
        except Exception as err_rule1:
            logger.warning(f"Rule 1 query warning: {err_rule1}")

        # -------------------------------------------------
        # Rule 2: Sudden sales drop (last 7 days vs previous 7 days <= -30%)
        # -------------------------------------------------
        sales_drop_query = f"""
            WITH ref AS (
                SELECT {ref_date_expr} AS max_date
            ),
            recent AS (
                SELECT {id_col}, SUM({qty_col}) AS qty
                FROM {sales_table}
                WHERE sale_date >= date((SELECT max_date FROM ref), '-7 days')
                GROUP BY {id_col}
            ),
            previous AS (
                SELECT {id_col}, SUM({qty_col}) AS qty
                FROM {sales_table}
                WHERE sale_date >= date((SELECT max_date FROM ref), '-14 days')
                  AND sale_date < date((SELECT max_date FROM ref), '-7 days')
                GROUP BY {id_col}
            )
            SELECT 
                p.{id_col} AS prod_id,
                p.{name_col} AS prod_name,
                r.qty AS recent_qty,
                prev.qty AS previous_qty,
                ROUND((r.qty - prev.qty) * 100.0 / NULLIF(prev.qty, 0), 1) AS pct_change
            FROM products p
            JOIN recent r ON p.{id_col} = r.{id_col}
            JOIN previous prev ON p.{id_col} = prev.{id_col}
            WHERE prev.qty > 0
              AND (r.qty - prev.qty) * 100.0 / prev.qty <= -30
            ORDER BY pct_change ASC
            LIMIT 10
        """

        try:
            drop_results = cursor.execute(sales_drop_query).fetchall()
            for row in drop_results:
                pct_change = row["pct_change"]
                prod_name = row["prod_name"]
                prod_id = row["prod_id"]
                recent_qty = row["recent_qty"]
                previous_qty = row["previous_qty"]

                seen_products.add(str(prod_id))
                rec_action = f"Run promotional campaign or review price strategy for {prod_name}"
                insights.append({
                    "insight_type": "sales_drop",
                    "title": f"Sales drop detected for {prod_name}",
                    "description": f"Sales fell {abs(pct_change)}% compared to the previous week (from {previous_qty} to {recent_qty} units).",
                    "severity": "high" if abs(pct_change) >= 50 else "medium",
                    "product_id": str(prod_id),
                    "product_name": str(prod_name),
                    "sku": str(prod_id),
                    "recommended_action": rec_action,
                    "suggested_reorder_qty": 0
                })
        except Exception as err_rule2:
            logger.warning(f"Rule 2 query warning: {err_rule2}")

        # -------------------------------------------------
        # Rule 3: High-Risk Items (stock <= reorder point or 0 stock)
        # -------------------------------------------------
        high_risk_query = f"""
            SELECT 
                p.{id_col} AS prod_id,
                p.{name_col} AS prod_name,
                i.{stock_col} AS current_stock,
                i.reorder_point
            FROM products p
            JOIN inventory i ON p.{id_col} = i.{id_col}
            WHERE i.{stock_col} <= i.reorder_point OR i.{stock_col} = 0
            ORDER BY i.{stock_col} ASC
            LIMIT 10
        """
        try:
            risk_results = cursor.execute(high_risk_query).fetchall()
            for row in risk_results:
                prod_id = str(row["prod_id"])
                if prod_id in seen_products:
                    continue
                prod_name = row["prod_name"]
                current_stock = int(row["current_stock"] or 0)
                reorder_pt = int(row["reorder_point"] or 5)

                reorder_qty = calculate_reorder_qty(current_stock, reorder_pt)
                rec_action = f"Reorder {reorder_qty} units immediately"

                if current_stock == 0:
                    severity = "critical"
                    title = f"{prod_name} is out of stock"
                    desc = f"Current stock is 0 units (Reorder point: {reorder_pt} units)."
                else:
                    severity = "high"
                    title = f"High Risk: {prod_name}"
                    desc = f"Product is at high risk. Current stock is {current_stock} units (Reorder point: {reorder_pt} units)."

                insights.append({
                    "insight_type": "high_risk",
                    "title": title,
                    "description": desc,
                    "severity": severity,
                    "product_id": prod_id,
                    "product_name": str(prod_name),
                    "sku": prod_id,
                    "recommended_action": rec_action,
                    "suggested_reorder_qty": reorder_qty
                })
        except Exception as err_rule3:
            logger.warning(f"Rule 3 query warning: {err_rule3}")

        # Compute proactive summary headline
        urgent_products = {ins["product_id"] for ins in insights if ins.get("severity") in ("high", "critical")}
        urgent_count = len(urgent_products)
        
        if urgent_count > 0:
            summary_headline = f"{urgent_count} products need urgent attention today"
        else:
            summary_headline = "All systems normal: inventory & sales performing smoothly today"

        # -------------------------------------------------
        # Save insights into auto_insights table (deduplicated)
        # -------------------------------------------------
        inserted_count = 0
        newly_inserted_insights = []
        now_str = datetime.now().strftime("%Y%m%d%H%M%S")

        for idx, insight in enumerate(insights):
            check_query = """
                SELECT 1 FROM auto_insights
                WHERE insight_type = ?
                  AND (product_id = ? OR sku = ?)
                  AND date(created_at) = date('now')
                LIMIT 1
            """
            exists = cursor.execute(check_query, (
                insight["insight_type"],
                insight.get("product_id"),
                insight.get("sku")
            )).fetchone()

            if not exists:
                insight_id = f"INS-{now_str}-{idx+1:03d}"
                payload = json.dumps(insight)

                rec_act = insight.get("recommended_action", "")
                reorder_qty = insight.get("suggested_reorder_qty", 0)

                pragma_ai = cursor.execute("PRAGMA table_info(auto_insights)").fetchall()
                ai_cols = {row[1] for row in pragma_ai}

                if "recommended_action" in ai_cols and "suggested_reorder_qty" in ai_cols:
                    cursor.execute("""
                        INSERT INTO auto_insights
                        (insight_id, domain, insight_type, title, description, severity,
                         product_id, product_name, sku, payload_json, recommended_action, suggested_reorder_qty, status, is_read, created_at)
                        VALUES (?, 'retail_clothing', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0, CURRENT_TIMESTAMP)
                    """, (
                        insight_id,
                        insight["insight_type"],
                        insight["title"],
                        insight["description"],
                        insight["severity"],
                        insight.get("product_id"),
                        insight.get("product_name"),
                        insight.get("sku"),
                        payload,
                        rec_act,
                        reorder_qty
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO auto_insights
                        (insight_id, domain, insight_type, title, description, severity,
                         product_id, product_name, sku, payload_json, status, is_read, created_at)
                        VALUES (?, 'retail_clothing', ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0, CURRENT_TIMESTAMP)
                    """, (
                        insight_id,
                        insight["insight_type"],
                        insight["title"],
                        insight["description"],
                        insight["severity"],
                        insight.get("product_id"),
                        insight.get("product_name"),
                        insight.get("sku"),
                        payload
                    ))
                
                # Check if auto_insights_spec exists, sync insert
                spec_exists = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_insights_spec'").fetchone()
                if spec_exists:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO auto_insights_spec
                            (insight_id, domain, insight_type, severity, title, description,
                             confidence, confidence_explanation, rule_version,
                             product_id, product_name, sku, payload_json, status, is_read, created_at)
                            VALUES (?, 'retail_clothing', ?, ?, ?, ?, 0.9, 'Rule engine evaluation', '1.0', ?, ?, ?, ?, 'ACTIVE', 0, CURRENT_TIMESTAMP)
                        """, (
                            insight_id,
                            insight["insight_type"],
                            insight["severity"].upper(),
                            insight["title"],
                            insight["description"],
                            insight.get("product_id"),
                            insight.get("product_name"),
                            insight.get("sku"),
                            payload
                        ))
                    except Exception as ex_spec:
                        logger.warning(f"auto_insights_spec sync insert warning: {ex_spec}")

                inserted_count += 1
                newly_inserted_insights.append(insight)

        conn.commit()
        logger.info(f"Auto Insights: Generated {len(insights)} insights, stored {inserted_count} new insights. Headline: '{summary_headline}'")

        # Dispatch notifications for detected high/critical insights
        if insights:
            _dispatch_notifications_sync(insights, summary_headline)

        return insights

    except Exception as e:
        logger.error(f"Error generating insights for {db_path}: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    generate_insights("retail_clothing.db")
