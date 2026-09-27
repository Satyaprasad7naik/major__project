"""
Stockout Risk Model — Hybrid ML + Rule-Based Scorer
=====================================================
Combines demand forecast output with inventory state and lead times
to produce risk levels and actionable insights.

Output: Risk Level (Critical/High/Medium/Low), Days of Cover, Stockout Probability
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from app.core.logger import logger


class StockoutRiskModel:
    """
    Hybrid stockout risk assessment engine.
    Uses demand predictions + business rules for risk classification.
    No external LLM dependency.
    """

    # Risk thresholds (days of cover)
    CRITICAL_THRESHOLD = 2
    HIGH_THRESHOLD = 5
    MEDIUM_THRESHOLD = 10

    def assess_risk(
        self,
        sku: str,
        current_stock: int,
        avg_daily_demand: float,
        lead_time_days: float,
        reorder_point: int,
        predicted_demand_7d: float = None,
    ) -> Dict[str, Any]:
        """
        Assess stockout risk for a single SKU.

        Returns:
            {
                "risk_level": "Critical" | "High" | "Medium" | "Low",
                "days_of_cover": float,
                "stockout_probability": float,
                "finding": str,
                "insight": str,
                "recommended_action": str,
                "confidence": float,
            }
        """
        # Calculate days of cover
        effective_demand = predicted_demand_7d / 7.0 if predicted_demand_7d else avg_daily_demand
        effective_demand = max(effective_demand, 0.01)  # Avoid division by zero

        days_of_cover = current_stock / effective_demand

        # Stockout probability (logistic function based on days_of_cover vs lead_time)
        if lead_time_days > 0:
            cover_ratio = days_of_cover / lead_time_days
            # Sigmoid: high probability when cover < lead_time
            import math
            stockout_prob = 1.0 / (1.0 + math.exp(3 * (cover_ratio - 1.0)))
        else:
            stockout_prob = 0.5 if current_stock <= reorder_point else 0.1

        # Risk classification
        if days_of_cover <= self.CRITICAL_THRESHOLD:
            risk_level = "Critical"
            confidence = 0.95
        elif days_of_cover <= self.HIGH_THRESHOLD:
            risk_level = "High"
            confidence = 0.90
        elif days_of_cover <= self.MEDIUM_THRESHOLD:
            risk_level = "Medium"
            confidence = 0.80
        else:
            risk_level = "Low"
            confidence = 0.85

        # Also consider stock vs reorder point
        if current_stock <= 0:
            risk_level = "Critical"
            confidence = 0.99
            stockout_prob = 1.0
        elif current_stock <= reorder_point and risk_level == "Low":
            risk_level = "Medium"
            confidence = 0.75

        return {
            "risk_level": risk_level,
            "days_of_cover": round(days_of_cover, 1),
            "stockout_probability": round(stockout_prob, 3),
            "confidence": confidence,
        }

    def analyze_all_products(
        self,
        db_path: str = "retail_clothing.db",
        threshold_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Analyze stockout risk for all products in the database.
        Returns list of at-risk products with Finding/Insight/Recommended Action.
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        try:
            products = conn.execute("""
                SELECT
                    p.sku, p.style_name, p.category, p.size, p.color, p.supplier_id,
                    i.stock_count, i.reorder_point, i.location,
                    s.supplier_name, s.lead_time_days, s.on_time_rate
                FROM products p
                JOIN inventory i ON p.sku = i.sku
                JOIN suppliers s ON p.supplier_id = s.supplier_id
                WHERE i.stock_count >= 0
            """).fetchall()

            results = []
            for product in products:
                sku = product["sku"]
                stock = product["stock_count"]
                reorder_pt = product["reorder_point"]
                lead_time = product["lead_time_days"]

                # Get average daily sales
                cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                sales_row = conn.execute(
                    "SELECT COALESCE(SUM(units_sold), 0) / 30.0 as avg_daily "
                    "FROM sales_events WHERE sku = ? AND sale_date >= ?",
                    (sku, cutoff),
                ).fetchone()
                avg_daily = float(sales_row["avg_daily"]) if sales_row else 0

                # Assess risk
                risk = self.assess_risk(
                    sku=sku,
                    current_stock=stock,
                    avg_daily_demand=avg_daily,
                    lead_time_days=lead_time,
                    reorder_point=reorder_pt,
                )

                # Only include at-risk products
                if risk["days_of_cover"] <= threshold_days or stock <= reorder_pt:
                    # Generate reorder quantity
                    from app.ml_models.reorder_quantity.model import reorder_calculator
                    reorder_qty = reorder_calculator.calculate(
                        current_stock=stock,
                        reorder_point=reorder_pt,
                        avg_daily_demand=avg_daily,
                        lead_time_days=lead_time,
                    )

                    # Build Finding/Insight/Recommended Action
                    if avg_daily > 0:
                        finding = (
                            f"{product['style_name']} ({sku}) has "
                            f"{risk['days_of_cover']:.1f} days of cover remaining"
                        )
                        insight = (
                            f"Current stock ({stock}) will last only "
                            f"{risk['days_of_cover']:.1f} days at current sales velocity "
                            f"({avg_daily:.1f}/day). Supplier lead time is {lead_time} days."
                        )
                    else:
                        finding = (
                            f"{product['style_name']} ({sku}) is at or below reorder point"
                        )
                        insight = (
                            f"Stock count ({stock}) has reached reorder threshold "
                            f"({reorder_pt}). Immediate reorder needed."
                        )

                    recommended_action = (
                        f"Reorder {reorder_qty} units from {product['supplier_name']} "
                        f"(lead time: {lead_time} days)"
                    )

                    results.append({
                        "sku": sku,
                        "style_name": product["style_name"],
                        "category": product["category"],
                        "size": product["size"],
                        "color": product["color"],
                        "location": product["location"],
                        "stock_count": stock,
                        "reorder_point": reorder_pt,
                        "days_of_cover": risk["days_of_cover"],
                        "avg_daily_sales": round(avg_daily, 1) if avg_daily > 0 else None,
                        "reorder_qty": reorder_qty,
                        "supplier_id": product["supplier_id"],
                        "supplier_name": product["supplier_name"],
                        "lead_time_days": lead_time,
                        "on_time_rate": product["on_time_rate"],
                        "finding": finding,
                        "insight": insight,
                        "recommended_action": recommended_action,
                        "confidence": risk["confidence"],
                        "risk_level": risk["risk_level"],
                        "stockout_probability": risk["stockout_probability"],
                        "method_used": "custom_hybrid_model",
                    })

            # Sort by urgency
            results.sort(key=lambda x: (
                {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(x["risk_level"], 4),
                x["days_of_cover"],
            ))

            logger.info(f"[StockoutRisk] Analyzed {len(products)} products, {len(results)} at-risk")
            return results

        finally:
            conn.close()


# Singleton instance
stockout_risk_model = StockoutRiskModel()
stockout_risk_scorer = stockout_risk_model
