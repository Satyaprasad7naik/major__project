"""
app/api/supply_chain_endpoints.py
==================================
Supply Chain Digital Twin API endpoints (Phase 3 of AGENTS.md roadmap).

Endpoints:
    GET  /api/v1/inventory/availability/{sku}    — real-time stock across warehouses
    POST /api/v1/inventory/route                 — fulfillment routing decision
    GET  /api/v1/inventory/overstock/{sku}       — find overstocked warehouses for re-routing
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.supply_chain import SupplyChainService
from app.core.logger import logger

router = APIRouter(prefix="/api/v1/inventory", tags=["supply-chain"])

_service = SupplyChainService()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class AvailabilityResponse(BaseModel):
    sku: str
    warehouse_id: str
    warehouse_name: str
    warehouse_city: str
    quantity_available: int
    quantity_in_transit: int
    is_available: bool
    click_collect_ready: bool
    reorder_needed: bool
    last_restocked_at: Optional[str]


class RouteRequest(BaseModel):
    sku: str = Field(..., description="Product SKU to fulfil")
    quantity: int = Field(1, ge=1, description="Number of units needed")
    customer_lat: Optional[float] = Field(None, description="Customer latitude for distance routing")
    customer_lon: Optional[float] = Field(None, description="Customer longitude for distance routing")
    customer_city: str = Field("", description="Customer city (for display)")
    fulfillment_type: str = Field("standard", description="standard | click_collect | express")


class FulfillmentRouteResponse(BaseModel):
    order_id: str
    sku: str
    quantity: int
    assigned_warehouse_id: str
    assigned_warehouse_name: str
    assigned_warehouse_city: str
    distance_km: float
    fulfillment_type: str
    estimated_carbon_kg: float
    reasoning: str
    created_at: str


class OverstockEntry(BaseModel):
    warehouse_id: str
    name: str
    city: str
    available: int
    reorder_point: int


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/availability/{sku}", response_model=list[AvailabilityResponse])
async def get_availability(sku: str):
    """
    Get real-time inventory availability for a SKU across all active warehouses.

    Returns one entry per warehouse, sorted by available quantity (descending).
    Use this to populate click-and-collect availability indicators on product pages.
    """
    try:
        results = _service.get_availability(sku)
        return [AvailabilityResponse(**r.__dict__) for r in results]
    except Exception as exc:
        logger.error(f"Availability check failed for SKU {sku}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Availability check error: {exc}")


@router.post("/route", response_model=FulfillmentRouteResponse)
async def route_fulfillment(body: RouteRequest):
    """
    Route a fulfillment order to the nearest warehouse with sufficient stock.

    - Provides the optimal warehouse assignment using Haversine distance when
      customer coordinates are available.
    - Falls back to highest-stock warehouse if coordinates are not supplied.
    - Estimates CO2 emissions for the shipment.
    - Persists the fulfillment order in the supply chain database.

    Returns **404** if no warehouse can fulfil the requested quantity.
    """
    try:
        route = _service.route_fulfillment(
            sku=body.sku,
            quantity=body.quantity,
            customer_lat=body.customer_lat,
            customer_lon=body.customer_lon,
            customer_city=body.customer_city,
            fulfillment_type=body.fulfillment_type,
        )
        if route is None:
            raise HTTPException(
                status_code=404,
                detail=f"No warehouse can fulfil {body.quantity} units of SKU '{body.sku}'",
            )
        return FulfillmentRouteResponse(**route.__dict__)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Fulfillment routing failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Routing error: {exc}")


@router.get("/overstock/{sku}", response_model=list[OverstockEntry])
async def get_overstock(
    sku: str,
    threshold_multiplier: float = Query(
        3.0,
        ge=1.0,
        description="Warehouses with stock > reorder_point * threshold are considered overstocked",
    ),
):
    """
    Identify warehouses holding significantly more stock than needed for a SKU.

    Use this to trigger backend webhooks that re-route overstock to warehouses
    with low inventory, preventing dead-stock accumulation.
    """
    try:
        results = _service.get_overstock_warehouses(sku, threshold_multiplier)
        return [OverstockEntry(**r) for r in results]
    except Exception as exc:
        logger.error(f"Overstock query failed for SKU {sku}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Overstock query error: {exc}")
