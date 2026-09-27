"""
Reorder Quantity Model — Rule-Based Calculator
================================================
Implements the simple, explainable reorder formula from context.md:

    if current_stock <= 0:
        qty = max(reorder_point * 3, 15)
    elif current_stock < reorder_point:
        qty = (reorder_point - current_stock) + reorder_point
    else:
        qty = 0

Extended with lead-time coverage for better accuracy.
"""

from typing import Optional
from app.core.logger import logger


class ReorderQuantityModel:
    """
    Rule-based reorder quantity calculator.
    Simple and explainable — perfect for academic evaluation.
    """

    def calculate(
        self,
        current_stock: int,
        reorder_point: int,
        avg_daily_demand: float = 0,
        lead_time_days: float = 7,
        safety_multiplier: float = 1.5,
    ) -> int:
        """
        Calculate recommended reorder quantity.

        Args:
            current_stock: Current units in stock
            reorder_point: Minimum stock threshold
            avg_daily_demand: Average daily sales rate
            lead_time_days: Supplier lead time in days
            safety_multiplier: Buffer multiplier for lead time coverage

        Returns:
            Recommended reorder quantity (int, >= 0)
        """
        # Primary formula from context.md
        if current_stock <= 0:
            qty = max(reorder_point * 3, 15)
        elif current_stock < reorder_point:
            qty = (reorder_point - current_stock) + reorder_point
        else:
            qty = 0

        # Enhanced: Lead-time coverage check
        if avg_daily_demand > 0 and qty > 0:
            lead_time_coverage = int(
                lead_time_days * avg_daily_demand * safety_multiplier
            )
            qty = max(qty, lead_time_coverage)

        logger.info(
            f"[ReorderQty] stock={current_stock}, reorder_pt={reorder_point}, "
            f"demand={avg_daily_demand:.1f}/day -> reorder={qty}"
        )

        return int(qty)

    def calculate_batch(
        self,
        products: list,
    ) -> list:
        """
        Calculate reorder quantities for a batch of products.

        Args:
            products: List of dicts with keys:
                      sku, current_stock, reorder_point,
                      avg_daily_demand (optional), lead_time_days (optional)

        Returns:
            List of dicts with sku and reorder_qty
        """
        results = []
        for p in products:
            qty = self.calculate(
                current_stock=p.get("current_stock", 0),
                reorder_point=p.get("reorder_point", 10),
                avg_daily_demand=p.get("avg_daily_demand", 0),
                lead_time_days=p.get("lead_time_days", 7),
            )
            results.append({
                "sku": p.get("sku", "UNKNOWN"),
                "current_stock": p.get("current_stock", 0),
                "reorder_point": p.get("reorder_point", 10),
                "reorder_qty": qty,
                "method": "rule_based_with_lead_time",
            })
        return results


# Singleton instance
reorder_calculator = ReorderQuantityModel()
