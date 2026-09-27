"""
app/modules/supply_chain.py
============================
Supply Chain Digital Twin service (Phase 3 of AGENTS.md roadmap).

Provides:
  - Real-time inventory availability checks (quantity_on_hand - quantity_reserved)
  - Nearest-warehouse fulfillment routing (Haversine distance ranking)
  - Click-and-collect availability indicators
  - Overstock re-routing webhooks (find warehouse with surplus stock)

The service lazily initialises the supply_chain schema on first call
so existing databases are migrated automatically.
"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.core.config import settings
from app.core.logger import logger
from app.services.database import DatabaseService


# ─────────────────────────────────────────────────────────────────────────────
# Haversine helper
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InventoryAvailability:
    sku: str
    warehouse_id: str
    warehouse_name: str
    warehouse_city: str
    quantity_available: int    # on_hand - reserved
    quantity_in_transit: int
    is_available: bool
    click_collect_ready: bool  # True when qty_available >= 1
    reorder_needed: bool
    last_restocked_at: Optional[str]


@dataclass
class FulfillmentRoute:
    order_id: str
    sku: str
    quantity: int
    assigned_warehouse_id: str
    assigned_warehouse_name: str
    assigned_warehouse_city: str
    distance_km: float
    fulfillment_type: str      # standard | click_collect | express
    estimated_carbon_kg: float
    reasoning: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class SupplyChainService:
    """
    Supply Chain Digital Twin service.

    Virtualises warehouse reserves, in-transit batches, and physical shelf stock.
    Routes fulfillment orders to the nearest warehouse holding sufficient stock.
    """

    # Emission factor: kg CO2 per km per unit (road freight average)
    _EMISSION_FACTOR_KG_PER_KM = 0.00012

    def __init__(self):
        self._db = DatabaseService()
        self._ensure_schema()

    # ── Schema init ───────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Apply supply_chain_schema.sql if tables don't exist yet."""
        schema_path = settings.SUPPLY_CHAIN_SCHEMA_PATH
        if not os.path.exists(schema_path):
            logger.warning(f"SupplyChainService: schema file not found at {schema_path}")
            return
        try:
            with self._db.engine.connect() as conn:
                # Quick existence check
                result = conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='warehouses'")
                )
                if result.fetchone() is None:
                    sql = open(schema_path).read()
                    for stmt in sql.split(";"):
                        stmt = stmt.strip()
                        if stmt:
                            conn.execute(text(stmt))
                    conn.commit()
                    logger.info("SupplyChainService: schema initialised")
        except Exception as exc:
            logger.error(f"SupplyChainService: schema init failed: {exc}")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_availability(self, sku: str) -> list[InventoryAvailability]:
        """
        Return availability data for *sku* across all active warehouses.
        """
        try:
            rows = self._db.execute_query(
                """
                SELECT
                    i.warehouse_id,
                    w.name,
                    w.city,
                    i.quantity_on_hand,
                    i.quantity_reserved,
                    i.quantity_in_transit,
                    i.reorder_point,
                    i.last_restocked_at
                FROM inventory_items i
                JOIN warehouses w ON w.warehouse_id = i.warehouse_id
                WHERE i.sku = :sku AND w.is_active = 1
                ORDER BY (i.quantity_on_hand - i.quantity_reserved) DESC
                """,
                {"sku": sku},
            )
        except Exception as exc:
            logger.error(f"SupplyChainService.get_availability({sku}): {exc}")
            return []

        results: list[InventoryAvailability] = []
        for row in rows:
            wh_id, wh_name, wh_city, on_hand, reserved, in_transit, reorder_pt, restocked = row
            available = max(0, on_hand - reserved)
            results.append(InventoryAvailability(
                sku=sku,
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                warehouse_city=wh_city,
                quantity_available=available,
                quantity_in_transit=in_transit,
                is_available=available > 0,
                click_collect_ready=available >= 1,
                reorder_needed=available <= reorder_pt,
                last_restocked_at=str(restocked) if restocked else None,
            ))
        return results

    def route_fulfillment(
        self,
        sku: str,
        quantity: int,
        customer_lat: Optional[float] = None,
        customer_lon: Optional[float] = None,
        customer_city: str = "",
        fulfillment_type: str = "standard",
    ) -> Optional[FulfillmentRoute]:
        """
        Route a fulfillment order to the nearest warehouse with sufficient stock.

        Uses Haversine distance when customer coordinates are provided;
        falls back to highest-available-stock warehouse otherwise.

        Returns None if no warehouse can fulfil the order.
        """
        availability = self.get_availability(sku)
        candidates = [a for a in availability if a.quantity_available >= quantity]
        if not candidates:
            logger.warning(f"SupplyChainService.route_fulfillment: no stock for {sku} qty={quantity}")
            return None

        # If we have coordinates, rank by distance; else by stock level
        if customer_lat is not None and customer_lon is not None:
            try:
                wh_coords = self._get_warehouse_coords()
                candidates.sort(
                    key=lambda a: _haversine_km(
                        customer_lat, customer_lon,
                        *wh_coords.get(a.warehouse_id, (customer_lat, customer_lon))
                    )
                )
            except Exception:
                candidates.sort(key=lambda a: -a.quantity_available)
        else:
            candidates.sort(key=lambda a: -a.quantity_available)

        best = candidates[0]

        # Estimate distance and carbon
        dist_km = 0.0
        if customer_lat is not None and customer_lon is not None:
            wh_coords = self._get_warehouse_coords()
            coords = wh_coords.get(best.warehouse_id)
            if coords:
                dist_km = _haversine_km(customer_lat, customer_lon, *coords)

        carbon_kg = round(dist_km * quantity * self._EMISSION_FACTOR_KG_PER_KM, 4)

        # Persist the fulfillment order
        order_id = f"FO-{uuid.uuid4().hex[:8].upper()}"
        try:
            self._db.execute_query(
                """
                INSERT INTO fulfillment_orders
                    (order_id, sku, quantity, customer_city, source_warehouse, fulfillment_type, status, carbon_kg)
                VALUES (:oid, :sku, :qty, :city, :wh, :ft, 'pending', :co2)
                """,
                {
                    "oid": order_id, "sku": sku, "qty": quantity,
                    "city": customer_city, "wh": best.warehouse_id,
                    "ft": fulfillment_type, "co2": carbon_kg,
                },
            )
        except Exception as exc:
            logger.warning(f"SupplyChainService: could not persist fulfillment order: {exc}")

        return FulfillmentRoute(
            order_id=order_id,
            sku=sku,
            quantity=quantity,
            assigned_warehouse_id=best.warehouse_id,
            assigned_warehouse_name=best.warehouse_name,
            assigned_warehouse_city=best.warehouse_city,
            distance_km=round(dist_km, 2),
            fulfillment_type=fulfillment_type,
            estimated_carbon_kg=carbon_kg,
            reasoning=(
                f"Routed to {best.warehouse_name} ({best.warehouse_city}) — "
                f"{best.quantity_available} units available, "
                f"{dist_km:.0f} km from customer."
            ),
        )

    def get_overstock_warehouses(self, sku: str, threshold_multiplier: float = 3.0) -> list[dict]:
        """
        Find warehouses holding more than *threshold_multiplier* x the reorder point
        (i.e. significantly overstocked) for re-routing surplus to needy locations.
        """
        try:
            rows = self._db.execute_query(
                """
                SELECT i.warehouse_id, w.name, w.city,
                       (i.quantity_on_hand - i.quantity_reserved) AS available,
                       i.reorder_point
                FROM inventory_items i
                JOIN warehouses w ON w.warehouse_id = i.warehouse_id
                WHERE i.sku = :sku
                  AND w.is_active = 1
                  AND (i.quantity_on_hand - i.quantity_reserved) > (i.reorder_point * :mult)
                ORDER BY available DESC
                """,
                {"sku": sku, "mult": threshold_multiplier},
            )
        except Exception as exc:
            logger.error(f"SupplyChainService.get_overstock_warehouses: {exc}")
            return []

        return [
            {"warehouse_id": r[0], "name": r[1], "city": r[2], "available": r[3], "reorder_point": r[4]}
            for r in rows
        ]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_warehouse_coords(self) -> dict[str, tuple[float, float]]:
        """Return {warehouse_id: (lat, lon)} for all active warehouses."""
        try:
            rows = self._db.execute_query(
                "SELECT warehouse_id, latitude, longitude FROM warehouses WHERE is_active = 1"
            )
            return {r[0]: (r[1], r[2]) for r in rows if r[1] is not None and r[2] is not None}
        except Exception:
            return {}
