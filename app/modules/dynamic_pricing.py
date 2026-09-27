"""
app/modules/dynamic_pricing.py
===============================
Dynamic Pricing Engine (Phase 2 of AGENTS.md roadmap).

Calculates real-time SKU price recommendations based on:
  - Inventory velocity (recent transaction count from the DB)
  - Base price from catalog data
  - Seasonal multipliers (month-of-year based)
  - Demand elasticity thresholds

The engine is intentionally stateless — each call re-reads the DB so it
reflects live inventory changes without stale in-memory cache.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.logger import logger
from app.services.database import DatabaseService


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PriceRecommendation:
    sku: str
    base_price: float
    recommended_price: float
    discount_pct: float          # negative = surcharge; positive = discount
    confidence: float            # 0.0 – 1.0
    velocity_score: float        # normalised 0.0 – 1.0 (higher = selling fast)
    reasoning: str
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class BatchPriceRequest:
    skus: list[str]
    override_base_prices: Optional[dict[str, float]] = None   # sku -> price, optional


# ─────────────────────────────────────────────────────────────────────────────
# Seasonal multipliers (month 1-12 → price factor)
# Reflects demand peaks: e.g. Dec holiday season, Jan sale, etc.
# ─────────────────────────────────────────────────────────────────────────────

_SEASONAL_FACTORS: dict[int, float] = {
    1:  0.90,   # January — post-holiday clearance
    2:  0.95,
    3:  1.00,
    4:  1.02,
    5:  1.03,
    6:  1.05,   # summer
    7:  1.08,
    8:  1.05,
    9:  1.00,
    10: 1.02,
    11: 1.10,   # pre-holiday build-up
    12: 1.15,   # peak holiday season
}


# ─────────────────────────────────────────────────────────────────────────────
# Pricing Engine
# ─────────────────────────────────────────────────────────────────────────────

class DynamicPricingEngine:
    """
    Algorithmic elasticity pricing engine.

    Instantiate once and call :meth:`get_price` or :meth:`get_batch_prices`
    for real-time recommendations.
    """

    # Transaction count thresholds (within the lookback window) that
    # define velocity buckets.
    _VELOCITY_HIGH = 50
    _VELOCITY_MED  = 20
    _VELOCITY_LOW  = 5

    # Price adjustment bounds
    _MAX_SURCHARGE_PCT  = 20.0   # never raise price more than 20%
    _MAX_DISCOUNT_PCT   = 30.0   # never drop price more than 30%

    # Lookback window for velocity calculation (seconds)
    _VELOCITY_WINDOW_SEC = 24 * 60 * 60   # 24 h

    def __init__(self):
        self._db = DatabaseService()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_price(
        self,
        sku: str,
        base_price: Optional[float] = None,
    ) -> PriceRecommendation:
        """
        Return a price recommendation for a single SKU.

        Args:
            sku: Product SKU identifier.
            base_price: Optional override; if None the engine attempts to
                        look up the SKU from the inventory/transactions data.
        """
        if base_price is None:
            base_price = self._lookup_base_price(sku)

        velocity = self._compute_velocity(sku)
        adjustment, reasoning = self._compute_adjustment(velocity)
        seasonal_factor = _SEASONAL_FACTORS.get(datetime.utcnow().month, 1.0)

        # Apply both velocity and seasonal adjustments
        raw_price = base_price * (1 + adjustment / 100) * seasonal_factor

        # Clamp to bounds
        min_price = base_price * (1 - self._MAX_DISCOUNT_PCT / 100)
        max_price = base_price * (1 + self._MAX_SURCHARGE_PCT / 100)
        recommended = max(min_price, min(max_price, raw_price))

        discount_pct = round((base_price - recommended) / base_price * 100, 2)
        confidence = self._confidence_score(velocity)

        if seasonal_factor != 1.0:
            direction = "premium" if seasonal_factor > 1 else "discount"
            reasoning += f" Seasonal {direction} applied ({seasonal_factor:.0%})."

        return PriceRecommendation(
            sku=sku,
            base_price=round(base_price, 2),
            recommended_price=round(recommended, 2),
            discount_pct=discount_pct,
            confidence=round(confidence, 3),
            velocity_score=round(velocity, 3),
            reasoning=reasoning,
        )

    def get_batch_prices(self, request: BatchPriceRequest) -> list[PriceRecommendation]:
        """Compute price recommendations for a list of SKUs."""
        results: list[PriceRecommendation] = []
        overrides = request.override_base_prices or {}
        for sku in request.skus:
            try:
                rec = self.get_price(sku, base_price=overrides.get(sku))
                results.append(rec)
            except Exception as exc:
                logger.warning(f"DynamicPricingEngine: failed for SKU {sku}: {exc}")
                results.append(
                    PriceRecommendation(
                        sku=sku,
                        base_price=0.0,
                        recommended_price=0.0,
                        discount_pct=0.0,
                        confidence=0.0,
                        velocity_score=0.0,
                        reasoning=f"Pricing unavailable: {exc}",
                    )
                )
        return results

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _lookup_base_price(self, sku: str) -> float:
        """
        Attempt to derive a base price from recent transaction amounts for this SKU.
        Falls back to a default of 100.0 if no data is found.
        """
        try:
            rows = self._db.execute_query(
                """
                SELECT AVG(amount_usd)
                FROM transactions
                WHERE instrument = :sku
                  AND status = 'completed'
                LIMIT 1
                """,
                {"sku": sku},
            )
            if rows and rows[0][0] is not None:
                return float(rows[0][0])
        except Exception as exc:
            logger.debug(f"DynamicPricingEngine._lookup_base_price({sku}): {exc}")
        return 100.0   # safe default

    def _compute_velocity(self, sku: str) -> float:
        """
        Return normalised velocity score [0.0, 1.0] based on transaction
        count for the SKU in the last 24 hours.
        """
        try:
            rows = self._db.execute_query(
                """
                SELECT COUNT(*)
                FROM transactions
                WHERE instrument = :sku
                  AND created_at >= datetime('now', :window)
                """,
                {"sku": sku, "window": f"-{self._VELOCITY_WINDOW_SEC} seconds"},
            )
            if rows:
                count = int(rows[0][0])
                return min(count / self._VELOCITY_HIGH, 1.0)
        except Exception as exc:
            logger.debug(f"DynamicPricingEngine._compute_velocity({sku}): {exc}")
        return 0.0

    def _compute_adjustment(self, velocity: float) -> tuple[float, str]:
        """
        Map velocity score to a price adjustment percentage and reasoning text.

        Returns:
            (adjustment_pct, reasoning)  — adjustment_pct > 0 means surcharge.
        """
        if velocity >= 0.8:
            return 15.0, "High demand velocity — surge pricing applied."
        if velocity >= 0.5:
            return 7.0, "Moderate-to-high demand — slight price increase."
        if velocity >= 0.2:
            return 0.0, "Steady demand — base price maintained."
        if velocity > 0.0:
            return -10.0, "Low demand velocity — promotional discount applied."
        return -20.0, "No recent transactions — clearance discount applied."

    @staticmethod
    def _confidence_score(velocity: float) -> float:
        """Higher data availability = higher confidence."""
        # Confidence grows with velocity (more transactions = more data)
        # Floor at 0.3 (we always have seasonal data), ceiling at 0.95
        return max(0.30, min(0.95, 0.30 + velocity * 0.65))
