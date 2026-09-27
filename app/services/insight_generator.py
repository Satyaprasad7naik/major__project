"""
Insight Generator — Rule-Based Template Engine
================================================
Replaces LLM-based insight generation with deterministic templates.
Produces Finding -> Insight -> Recommended Action output grounded in live retail data.
"""

import json
from typing import Dict, Any, List
from app.core.logger import logger


class InsightGeneratorService:
    """
    Rule-based insight generator using templates per intent type.
    Produces executive-level insights without external LLM calls.
    """

    def generate(
        self,
        query: str,
        results: List[Dict[str, Any]],
        domain: str = "general",
        retail_intent: str = None,
    ) -> Dict[str, str]:
        """
        Generate insights from query results using rule-based templates.
        """
        if not results:
            return {
                "insight": "No data found matching your query criteria.",
                "recommendation": "Try broadening your search or check if data for this period is available.",
            }

        row_count = len(results)
        query_lower = query.lower()

        # Auto-detect intent from query if not provided
        if retail_intent is None:
            retail_intent = self._detect_intent(query_lower)

        # Route to appropriate template
        if retail_intent == "stockout_risk" or any(kw in query_lower for kw in ["stockout", "out of stock", "risk"]):
            return self._stockout_insight(results, row_count)
        elif retail_intent == "reorder_recommendation" or any(kw in query_lower for kw in ["reorder", "restock"]):
            return self._reorder_insight(results, row_count)
        elif any(kw in query_lower for kw in ["profit", "margin", "cost"]):
            return self._profit_insight(results, row_count)
        elif any(kw in query_lower for kw in ["shop", "store", "city", "location", "payment", "customer"]):
            return self._sales_insight(results, row_count, query_lower)
        elif retail_intent == "sales_analysis" or any(kw in query_lower for kw in ["sales", "revenue", "sold", "selling", "top"]):
            return self._sales_insight(results, row_count, query_lower)
        elif retail_intent == "inventory_status" or any(kw in query_lower for kw in ["inventory", "stock"]):
            return self._inventory_insight(results, row_count)
        else:
            return self._general_insight(results, row_count, query_lower)

    def _detect_intent(self, query_lower: str) -> str:
        """Simple keyword-based intent detection for template routing."""
        if any(kw in query_lower for kw in ["stockout", "risk", "out of stock", "low stock", "run out"]):
            return "stockout_risk"
        elif any(kw in query_lower for kw in ["reorder", "purchase order", "restock", "order"]):
            return "reorder_recommendation"
        elif any(kw in query_lower for kw in ["profit", "margin", "cost"]):
            return "profit_analysis"
        elif any(kw in query_lower for kw in ["sales", "revenue", "sold", "selling", "top", "shop", "city", "payment"]):
            return "sales_analysis"
        elif any(kw in query_lower for kw in ["inventory", "stock", "warehouse", "catalog"]):
            return "inventory_status"
        return "general_query"

    def _stockout_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate stockout / sales-velocity specific insights."""
        critical_items = []
        for r in results[:5]:
            name = r.get("product", r.get("style_name", r.get("sku", "Unknown")))
            units = r.get("total_units_sold", r.get("quantity", r.get("stock_count", "N/A")))
            rev = r.get("total_sales", r.get("sales", None))
            if rev is not None:
                critical_items.append(f"{name} ({units} units sold, ₹{rev:,.2f} sales)")
            else:
                critical_items.append(f"{name} ({units} units)")

        items_str = "; ".join(critical_items[:3])
        worst = results[0] if results else {}
        worst_name = worst.get("product", worst.get("style_name", worst.get("sku", "Top item")))
        worst_units = worst.get("total_units_sold", worst.get("quantity", "high volume"))

        return {
            "insight": (
                f"Identified {count} high-velocity products in the live dataset. "
                f"Top in demand: {items_str}. "
                f"'{worst_name}' leads demand with {worst_units} units sold and requires proactive inventory monitoring."
            ),
            "recommendation": (
                f"1. Ensure adequate inventory buffer for top high-velocity products ({worst_name}).\n"
                f"2. Monitor real-time sales rates across top selling categories.\n"
                f"3. Maintain supplier reorder cadences to prevent out-of-stock events."
            ),
        }

    def _reorder_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate reorder-specific insights."""
        total_qty = sum(r.get("suggested_reorder_qty", r.get("reorder_qty", 0)) for r in results)
        total_cost = sum(
            r.get("suggested_reorder_qty", r.get("reorder_qty", 0)) * r.get("unit_cost", 40)
            for r in results
        )

        return {
            "insight": (
                f"{count} products require immediate replenishment. "
                f"Total recommended reorder volume: {total_qty} units. "
                + (f"Estimated procurement value: ₹{total_cost:,.2f}. " if total_cost > 0 else "")
                + "Timely reordering prevents lost sales."
            ),
            "recommendation": (
                f"1. Approve purchase orders for all {count} items requiring replenishment.\n"
                f"2. Prioritize items with the highest demand velocity.\n"
                f"3. Consolidate supplier orders to optimize bulk freight costs."
            ),
        }

    def _profit_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate profit & margin specific insights."""
        top = results[0] if results else {}
        top_name = top.get("product", top.get("category", top.get("shop_name", "Top Item")))
        top_profit = top.get("total_profit", top.get("profit", 0.0))
        top_margin = top.get("profit_margin_pct", 0.0)

        total_profit = sum(r.get("total_profit", r.get("profit", 0.0)) for r in results)
        total_sales = sum(r.get("total_sales", r.get("sales", 0.0)) for r in results)

        return {
            "insight": (
                f"Profit analysis across {count} items. Top contributor: '{top_name}' "
                f"generating ₹{top_profit:,.2f} in net profit"
                + (f" ({top_margin}% margin)" if top_margin else "")
                + f". Total profit: ₹{total_profit:,.2f} on total sales of ₹{total_sales:,.2f}."
            ),
            "recommendation": (
                f"1. Promote high-margin items like '{top_name}' to maximize total gross margin.\n"
                f"2. Review cost structures for low-margin products.\n"
                f"3. Optimize procurement pricing with suppliers for top profit generators."
            ),
        }

    def _sales_insight(self, results: List[dict], count: int, query: str) -> Dict[str, str]:
        """Generate sales-specific insights."""
        top = results[0] if results else {}
        top_name = top.get("product", top.get("shop_name", top.get("city", top.get("category", top.get("payment_method", top.get("customer_type", top.get("style_name", top.get("sku", "Top Entity"))))))))
        top_units = top.get("total_units_sold", top.get("total_units", top.get("units_sold", top.get("quantity", top.get("transaction_count", top.get("num_transactions", "N/A"))))))
        top_revenue = top.get("total_sales", top.get("total_revenue", top.get("sales", top.get("estimated_revenue", "N/A"))))

        total_units = sum(
            r.get("total_units_sold", r.get("total_units", r.get("units_sold", r.get("quantity", 0))))
            for r in results
        )
        total_rev = sum(
            r.get("total_sales", r.get("total_revenue", r.get("sales", 0.0)))
            for r in results
        )

        return {
            "insight": (
                f"Sales analysis reveals {count} records in the dataset. "
                f"Leading entity: '{top_name}' with {top_units} units/transactions"
                + (f" generating ₹{top_revenue:,.2f} in revenue" if isinstance(top_revenue, (int, float)) else "")
                + (f". Total cumulative sales: ₹{total_rev:,.2f} ({total_units} total units)." if total_rev > 0 else "")
            ),
            "recommendation": (
                f"1. Ensure adequate inventory for '{top_name}' to maintain sales velocity.\n"
                f"2. Replicate successful merchandising and channel strategies across other segments.\n"
                f"3. Monitor conversion and velocity trends across all retail outlets."
            ),
        }

    def _inventory_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate inventory-specific insights."""
        total_stock = sum(r.get("stock_count", r.get("total_stock", r.get("stock", 0))) for r in results)
        low_stock = sum(
            1 for r in results
            if r.get("stock_count", 0) <= r.get("reorder_point", 0) or r.get("low_stock_count", 0) > 0
        )

        return {
            "insight": (
                f"Inventory snapshot: {count} product categories/items with a total of {total_stock} units in stock. "
                + (f"{low_stock} items/categories are at or below reorder threshold. " if low_stock > 0 else "")
                + f"Overall inventory posture is "
                + ("concerning" if low_stock > count * 0.3 else "moderate" if low_stock > 0 else "healthy")
                + "."
            ),
            "recommendation": (
                "1. Reorder products reaching safety thresholds.\n"
                "2. Monitor warehouse stock velocity to prevent stockouts.\n"
                "3. Align purchase orders with predicted 30-day demand."
            ),
        }

    def _general_insight(self, results: List[dict], count: int, query: str) -> Dict[str, str]:
        """Generate general insights for unspecified intents."""
        if results:
            columns = list(results[0].keys())
            col_str = ", ".join(columns[:6])
        else:
            col_str = "N/A"

        return {
            "insight": (
                f"Query returned {count} records matching '{query}'. "
                f"Columns included: {col_str}."
            ),
            "recommendation": (
                "1. Explore specific aggregations like top selling products, profit margins, or stockout alerts.\n"
                "2. Use targeted entity queries (e.g. by product, city, or category) for deeper analysis."
            ),
        }


# Singleton instance
insight_generator_service = InsightGeneratorService()
