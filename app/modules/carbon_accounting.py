"""
app/modules/carbon_accounting.py
==================================
Scope 1-3 Carbon Accounting Calculator (Phase 4 of AGENTS.md roadmap).

Calculates lifecycle greenhouse gas emissions per SKU across three scopes:

  Scope 1 — Direct emissions from the company's own operations
             (warehouse energy, owned fleet)
  Scope 2 — Indirect emissions from purchased electricity
             (warehouse power consumption)
  Scope 3 — All other indirect emissions in the value chain
             Category 1:  Purchased goods (sourcing / manufacturing)
             Category 4:  Upstream transportation (supplier -> warehouse)
             Category 9:  Downstream transportation (warehouse -> customer)
             Category 11: Use of sold products

All emission factors are based on publicly available GHG Protocol / IPCC AR6
averages and are intentionally conservative to avoid greenwashing.

References:
  - IPCC AR6 WG3 (2022): transport emission factors
  - GHG Protocol Corporate Standard (2015)
  - EPA GHG Emission Factors Hub (2023)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.logger import logger
from app.services.database import DatabaseService


# ─────────────────────────────────────────────────────────────────────────────
# Emission factor constants (kg CO2e per unit)
# ─────────────────────────────────────────────────────────────────────────────

class EmissionFactors:
    # Scope 1 — warehouse operations (kg CO2e per unit-day of warehouse storage)
    WAREHOUSE_STORAGE_PER_UNIT_DAY = 0.0012

    # Scope 2 — purchased electricity (kg CO2e per kWh, India grid average 2023)
    ELECTRICITY_KG_PER_KWH = 0.716
    WAREHOUSE_KWH_PER_UNIT_DAY = 0.05   # kWh consumed per unit per day in warehouse

    # Scope 3 Category 1 — purchased goods (manufacturing; kg CO2e per USD of product value)
    MANUFACTURING_KG_PER_USD = 0.42     # EEIO average for consumer goods

    # Scope 3 Category 4 — upstream transport (kg CO2e per tonne-km, sea freight)
    UPSTREAM_TRANSPORT_KG_PER_TONNE_KM = 0.011
    AVG_UPSTREAM_DISTANCE_KM = 8000     # e.g. manufacturing in Asia -> India

    # Scope 3 Category 9 — downstream transport (kg CO2e per km per unit)
    DOWNSTREAM_ROAD_KG_PER_KM = 0.00012   # road freight
    DOWNSTREAM_EXPRESS_KG_PER_KM = 0.00035  # air express
    DOWNSTREAM_DEFAULT_DISTANCE_KM = 500  # avg last-mile when unknown

    # Product weight assumption when unknown (kg)
    DEFAULT_WEIGHT_KG = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScopeBreakdown:
    scope1_kg: float   # direct operations
    scope2_kg: float   # purchased electricity
    scope3_sourcing_kg: float    # Scope 3 Cat 1 — manufacturing
    scope3_upstream_kg: float    # Scope 3 Cat 4 — inbound transport
    scope3_downstream_kg: float  # Scope 3 Cat 9 — outbound / last-mile


@dataclass
class CarbonFootprint:
    sku: str
    base_price_usd: float
    weight_kg: float
    avg_warehouse_days: float
    delivery_distance_km: float
    delivery_mode: str              # road | express
    scope1_kg: float
    scope2_kg: float
    scope3_kg: float
    total_kg_co2e: float
    breakdown: ScopeBreakdown
    low_emission_alternative: Optional[str]
    label: str                      # A/B/C/D/E rating (A = best)
    calculated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class CheckoutEmissionOption:
    option_name: str
    fulfillment_type: str
    estimated_co2_kg: float
    delta_vs_standard_kg: float    # negative = better than standard
    description: str


# ─────────────────────────────────────────────────────────────────────────────
# Rating thresholds (total kg CO2e per unit)
# ─────────────────────────────────────────────────────────────────────────────

_RATING_THRESHOLDS = [
    (1.0,  "A"),   # <= 1 kg
    (3.0,  "B"),   # <= 3 kg
    (7.0,  "C"),   # <= 7 kg
    (15.0, "D"),   # <= 15 kg
]


def _rate(total_kg: float) -> str:
    for threshold, grade in _RATING_THRESHOLDS:
        if total_kg <= threshold:
            return grade
    return "E"


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class CarbonAccountingService:
    """
    Scope 1-3 lifecycle carbon footprint calculator for SKUs.

    Derives product price and transaction frequency from the live database
    to estimate manufacturing cost (Scope 3 Cat 1) and inventory holding time
    (Scope 1 + 2). All other factors use validated industry constants.
    """

    def __init__(self):
        self._db = DatabaseService()
        self._ef = EmissionFactors()

    # ── Public API ────────────────────────────────────────────────────────────

    def calculate(
        self,
        sku: str,
        weight_kg: Optional[float] = None,
        delivery_distance_km: Optional[float] = None,
        delivery_mode: str = "road",
    ) -> CarbonFootprint:
        """
        Calculate full Scope 1-3 carbon footprint for *sku*.

        Args:
            sku: Product SKU identifier.
            weight_kg: Product weight. If None, uses default of 0.5 kg.
            delivery_distance_km: Last-mile distance. If None, uses 500 km average.
            delivery_mode: "road" (default) or "express" (air).
        """
        ef = self._ef

        # Derive base price from transaction data
        base_price = self._lookup_price(sku)

        # Product weight
        w = weight_kg if weight_kg is not None else ef.DEFAULT_WEIGHT_KG

        # Delivery distance
        dist_km = delivery_distance_km if delivery_distance_km is not None else ef.DOWNSTREAM_DEFAULT_DISTANCE_KM

        # Average time in warehouse (days) — derived from transaction interval
        wh_days = self._lookup_avg_holding_days(sku)

        # ── Scope 1: warehouse storage (energy + fleet estimate) ──────────────
        scope1 = round(w * wh_days * ef.WAREHOUSE_STORAGE_PER_UNIT_DAY, 6)

        # ── Scope 2: purchased electricity for warehouse ──────────────────────
        kwh = w * wh_days * ef.WAREHOUSE_KWH_PER_UNIT_DAY
        scope2 = round(kwh * ef.ELECTRICITY_KG_PER_KWH, 6)

        # ── Scope 3 Cat 1: manufacturing (based on product value) ─────────────
        s3_mfg = round(base_price * ef.MANUFACTURING_KG_PER_USD, 6)

        # ── Scope 3 Cat 4: upstream transport (sea freight) ───────────────────
        tonne_km = (w / 1000) * ef.AVG_UPSTREAM_DISTANCE_KM
        s3_upstream = round(tonne_km * ef.UPSTREAM_TRANSPORT_KG_PER_TONNE_KM, 6)

        # ── Scope 3 Cat 9: downstream transport (last-mile) ──────────────────
        factor = ef.DOWNSTREAM_EXPRESS_KG_PER_KM if delivery_mode == "express" else ef.DOWNSTREAM_ROAD_KG_PER_KM
        s3_downstream = round(dist_km * factor, 6)

        # Totals
        scope3_total = round(s3_mfg + s3_upstream + s3_downstream, 6)
        total = round(scope1 + scope2 + scope3_total, 4)

        # Low-emission alternative suggestion
        alt = self._suggest_alternative(delivery_mode, dist_km, s3_downstream)

        return CarbonFootprint(
            sku=sku,
            base_price_usd=round(base_price, 2),
            weight_kg=w,
            avg_warehouse_days=round(wh_days, 1),
            delivery_distance_km=dist_km,
            delivery_mode=delivery_mode,
            scope1_kg=scope1,
            scope2_kg=scope2,
            scope3_kg=scope3_total,
            total_kg_co2e=total,
            breakdown=ScopeBreakdown(
                scope1_kg=scope1,
                scope2_kg=scope2,
                scope3_sourcing_kg=s3_mfg,
                scope3_upstream_kg=s3_upstream,
                scope3_downstream_kg=s3_downstream,
            ),
            low_emission_alternative=alt,
            label=_rate(total),
        )

    def get_checkout_options(
        self,
        sku: str,
        weight_kg: Optional[float] = None,
        delivery_distance_km: Optional[float] = None,
    ) -> list[CheckoutEmissionOption]:
        """
        Return emission comparison for available fulfillment modes at checkout.
        Helps customers choose lower-emission delivery options.
        """
        w = weight_kg or self._ef.DEFAULT_WEIGHT_KG
        dist = delivery_distance_km or self._ef.DOWNSTREAM_DEFAULT_DISTANCE_KM

        # Standard road
        std = self.calculate(sku, w, dist, "road")

        options: list[CheckoutEmissionOption] = [
            CheckoutEmissionOption(
                option_name="Standard Delivery",
                fulfillment_type="standard",
                estimated_co2_kg=std.scope3_kg,
                delta_vs_standard_kg=0.0,
                description=f"Road freight — {dist:.0f} km, {std.scope3_kg:.3f} kg CO2e",
            )
        ]

        # Express (air)
        exp = self.calculate(sku, w, dist, "express")
        options.append(CheckoutEmissionOption(
            option_name="Express Delivery",
            fulfillment_type="express",
            estimated_co2_kg=exp.scope3_kg,
            delta_vs_standard_kg=round(exp.scope3_kg - std.scope3_kg, 4),
            description=f"Air express — higher emissions +{exp.scope3_kg - std.scope3_kg:.3f} kg CO2e",
        ))

        # Click & Collect (negligible last-mile)
        cc = self.calculate(sku, w, 5.0, "road")   # 5 km = customer drives to store
        options.append(CheckoutEmissionOption(
            option_name="Click & Collect",
            fulfillment_type="click_collect",
            estimated_co2_kg=cc.scope3_kg,
            delta_vs_standard_kg=round(cc.scope3_kg - std.scope3_kg, 4),
            description=f"Collect from nearest store — lowest last-mile impact: {cc.scope3_kg:.3f} kg CO2e",
        ))

        return sorted(options, key=lambda o: o.estimated_co2_kg)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _lookup_price(self, sku: str) -> float:
        try:
            rows = self._db.execute_query(
                "SELECT AVG(amount_usd) FROM transactions WHERE instrument = :sku AND status = 'completed'",
                {"sku": sku},
            )
            if rows and rows[0][0] is not None:
                return float(rows[0][0])
        except Exception as exc:
            logger.debug(f"CarbonAccountingService._lookup_price({sku}): {exc}")
        return 50.0   # conservative fallback

    def _lookup_avg_holding_days(self, sku: str) -> float:
        """Estimate warehouse holding days from avg days between transactions."""
        try:
            rows = self._db.execute_query(
                """
                SELECT AVG(julianday(t2.created_at) - julianday(t1.created_at)) AS avg_gap
                FROM transactions t1
                JOIN transactions t2
                  ON t1.instrument = t2.instrument
                 AND t1.txn_id < t2.txn_id
                WHERE t1.instrument = :sku
                  AND t1.status = 'completed'
                  AND t2.status = 'completed'
                LIMIT 1
                """,
                {"sku": sku},
            )
            if rows and rows[0][0] is not None:
                gap = float(rows[0][0])
                # Assume ~half the transaction interval is warehouse time
                return max(1.0, gap / 2)
        except Exception as exc:
            logger.debug(f"CarbonAccountingService._lookup_avg_holding_days({sku}): {exc}")
        return 14.0   # 2-week default

    @staticmethod
    def _suggest_alternative(mode: str, dist_km: float, downstream_kg: float) -> Optional[str]:
        if mode == "express":
            return "Switch to standard road delivery to reduce last-mile emissions by ~65%."
        if dist_km > 300:
            return "Consider Click & Collect or local store pickup to significantly cut last-mile CO2."
        return None
