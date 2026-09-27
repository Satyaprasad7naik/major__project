"""Stockout Risk Analysis Module for InsightOS."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sqlite3
from app.core.logger import logger

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_days_of_cover(stock_count: int, avg_daily_sales: float) -> float:
    """Calculate days of cover. Returns float('inf') if no sales."""
    if avg_daily_sales <= 0:
        return float('inf')
    return stock_count / avg_daily_sales

def calculate_reorder_qty(stock_count: int, reorder_point: int, lead_time_days: int, avg_daily_sales: float) -> int:
    """Calculate recommended reorder quantity."""
    # Method 1: Restock to 2x reorder point
    qty_to_2x_reorder = max(0, reorder_point * 2 - stock_count)

    # Method 2: Cover lead time + 50% buffer
    lead_time_coverage = int(lead_time_days * avg_daily_sales * 1.5) if avg_daily_sales > 0 else reorder_point * 2

    return max(qty_to_2x_reorder, lead_time_coverage)

def get_avg_daily_sales(conn: sqlite3.Connection, sku: str, days: int = 30) -> float:
    """Get average daily sales for a SKU over the last N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor = conn.execute(
        "SELECT SUM(units_sold) as total FROM sales_events WHERE sku = ? AND sale_date >= ?",
        (sku, cutoff_date)
    )
    row = cursor.fetchone()
    total_sold = row['total'] if row and row['total'] else 0
    return total_sold / days if days > 0 else 0

def analyze_stockout_risk(
    domain: str,
    threshold_days: int = 7,
    method: str = "auto",
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Analyze stockout risk for products in a domain.

    Args:
        domain: Domain name (e.g., 'retail_clothing')
        threshold_days: Days ahead to flag as at-risk
        method: 'simple' (reorder_point), 'days_of_cover', or 'auto'
        db_path: Optional database path (uses default if not provided)

    Returns:
        List of at-risk products with Finding, Insight, Recommended Action, Confidence
    """
    if db_path is None:
        # Default database paths per domain
        domain_db_map = {
            "retail_clothing": "retail_clothing.db",
            "banking_finance": "derivinsightnew.db",
            "insurance": "derivinsightnew.db",
        }
        db_path = domain_db_map.get(domain, "retail_clothing.db")

    conn = get_db_connection(db_path)
    results = []

    try:
        # Get all products with inventory and supplier info
        cursor = conn.execute("""
            SELECT
                p.sku, p.style_name, p.category, p.size, p.color, p.supplier_id,
                i.stock_count, i.reorder_point, i.location,
                s.supplier_name, s.lead_time_days, s.on_time_rate
            FROM products p
            JOIN inventory i ON p.sku = i.sku
            JOIN suppliers s ON p.supplier_id = s.supplier_id
            WHERE i.stock_count >= 0
        """)
        products = cursor.fetchall()

        for product in products:
            sku = product['sku']
            stock_count = product['stock_count']
            reorder_point = product['reorder_point']
            lead_time_days = product['lead_time_days']

            # Determine calculation method
            use_days_of_cover = False
            if method == "days_of_cover":
                use_days_of_cover = True
            elif method == "auto":
                # Check if sales history exists
                avg_daily = get_avg_daily_sales(conn, sku)
                use_days_of_cover = avg_daily > 0

            if use_days_of_cover:
                avg_daily_sales = get_avg_daily_sales(conn, sku)
                days_of_cover = calculate_days_of_cover(stock_count, avg_daily_sales)
                at_risk = days_of_cover <= threshold_days
            else:
                # Simple threshold method
                days_of_cover = float('inf')
                avg_daily_sales = 0
                at_risk = stock_count <= reorder_point

            if at_risk:
                reorder_qty = calculate_reorder_qty(stock_count, reorder_point, lead_time_days, avg_daily_sales)

                # Build Finding, Insight, Recommended Action
                if use_days_of_cover:
                    finding = f"{product['style_name']} ({sku}) has {days_of_cover:.1f} days of cover remaining"
                    insight = f"Current stock ({stock_count}) will last only {days_of_cover:.1f} days at current sales velocity ({avg_daily_sales:.1f}/day). Supplier lead time is {lead_time_days} days."
                else:
                    finding = f"{product['style_name']} ({sku}) is at or below reorder point"
                    insight = f"Stock count ({stock_count}) has reached reorder threshold ({reorder_point}). Immediate reorder needed to prevent stockout."

                recommended_action = f"Reorder {reorder_qty} units from {product['supplier_name']} (lead time: {lead_time_days} days)"

                # Confidence: higher when we have sales data
                confidence = 0.85 if use_days_of_cover else 0.7

                results.append({
                    "sku": sku,
                    "style_name": product['style_name'],
                    "category": product['category'],
                    "size": product['size'],
                    "color": product['color'],
                    "location": product['location'],
                    "stock_count": stock_count,
                    "reorder_point": reorder_point,
                    "days_of_cover": round(days_of_cover, 1) if days_of_cover != float('inf') else None,
                    "avg_daily_sales": round(avg_daily_sales, 1) if avg_daily_sales > 0 else None,
                    "reorder_qty": reorder_qty,
                    "supplier_id": product['supplier_id'],
                    "supplier_name": product['supplier_name'],
                    "lead_time_days": lead_time_days,
                    "on_time_rate": product['on_time_rate'],
                    "finding": finding,
                    "insight": insight,
                    "recommended_action": recommended_action,
                    "confidence": confidence,
                    "method_used": "days_of_cover" if use_days_of_cover else "simple_threshold"
                })

        # Sort by urgency (lowest days of cover first, then by stock level)
        results.sort(key=lambda x: (x['days_of_cover'] if x['days_of_cover'] else 999, x['stock_count']))

        logger.info(f"Stockout analysis for {domain}: {len(results)} at-risk products found")
        return results

    finally:
        conn.close()