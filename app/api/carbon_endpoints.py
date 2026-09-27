"""
app/api/carbon_endpoints.py
=============================
Scope 1-3 Carbon Accounting API endpoints (Phase 4 of AGENTS.md roadmap).

Endpoints:
    GET  /api/v1/carbon/{sku}                — full lifecycle carbon footprint for a SKU
    GET  /api/v1/carbon/checkout/options     — checkout delivery options ranked by emissions
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.carbon_accounting import CarbonAccountingService, ScopeBreakdown
from app.core.logger import logger

router = APIRouter(prefix="/api/v1/carbon", tags=["carbon-accounting"])

_service = CarbonAccountingService()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ScopeBreakdownResponse(BaseModel):
    scope1_kg: float = Field(description="Scope 1: direct warehouse & fleet emissions")
    scope2_kg: float = Field(description="Scope 2: purchased electricity (warehouse)")
    scope3_sourcing_kg: float = Field(description="Scope 3 Cat 1: manufacturing / purchased goods")
    scope3_upstream_kg: float = Field(description="Scope 3 Cat 4: upstream transport (inbound)")
    scope3_downstream_kg: float = Field(description="Scope 3 Cat 9: last-mile delivery")


class CarbonFootprintResponse(BaseModel):
    sku: str
    base_price_usd: float
    weight_kg: float
    avg_warehouse_days: float
    delivery_distance_km: float
    delivery_mode: str
    scope1_kg: float
    scope2_kg: float
    scope3_kg: float
    total_kg_co2e: float
    breakdown: ScopeBreakdownResponse
    low_emission_alternative: Optional[str]
    label: str = Field(description="Emissions rating: A (best) through E (worst)")
    calculated_at: str


class CheckoutOptionResponse(BaseModel):
    option_name: str
    fulfillment_type: str
    estimated_co2_kg: float
    delta_vs_standard_kg: float = Field(description="Negative = lower emissions than standard")
    description: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{sku}", response_model=CarbonFootprintResponse)
async def get_carbon_footprint(
    sku: str,
    weight_kg: Optional[float] = Query(None, ge=0.001, description="Product weight in kg. Defaults to 0.5 kg."),
    delivery_distance_km: Optional[float] = Query(None, ge=0.1, description="Last-mile delivery distance in km. Defaults to 500 km."),
    delivery_mode: str = Query("road", description="Delivery mode: 'road' (default) or 'express' (air)"),
):
    """
    Calculate the full **Scope 1-3 carbon footprint** for a single SKU.

    ### Scope coverage
    | Scope | Coverage |
    |---|---|
    | **Scope 1** | Warehouse operations, owned-fleet transport |
    | **Scope 2** | Purchased electricity for warehouse cooling/lighting |
    | **Scope 3 Cat 1** | Manufacturing emissions (derived from product value) |
    | **Scope 3 Cat 4** | Upstream transport (supplier → warehouse, sea freight) |
    | **Scope 3 Cat 9** | Last-mile delivery (road or air express) |

    ### Emissions rating
    | Label | Total CO2e |
    |---|---|
    | **A** | ≤ 1 kg |
    | **B** | ≤ 3 kg |
    | **C** | ≤ 7 kg |
    | **D** | ≤ 15 kg |
    | **E** | > 15 kg |
    """
    if not isinstance(delivery_mode, str) or delivery_mode not in ("road", "express"):
        delivery_mode = "road"
    if not isinstance(weight_kg, (int, float)):
        weight_kg = None
    if not isinstance(delivery_distance_km, (int, float)):
        delivery_distance_km = None
    try:
        fp = _service.calculate(
            sku=sku,
            weight_kg=weight_kg,
            delivery_distance_km=delivery_distance_km,
            delivery_mode=delivery_mode,
        )
        return CarbonFootprintResponse(
            sku=fp.sku,
            base_price_usd=fp.base_price_usd,
            weight_kg=fp.weight_kg,
            avg_warehouse_days=fp.avg_warehouse_days,
            delivery_distance_km=fp.delivery_distance_km,
            delivery_mode=fp.delivery_mode,
            scope1_kg=fp.scope1_kg,
            scope2_kg=fp.scope2_kg,
            scope3_kg=fp.scope3_kg,
            total_kg_co2e=fp.total_kg_co2e,
            breakdown=ScopeBreakdownResponse(**fp.breakdown.__dict__),
            low_emission_alternative=fp.low_emission_alternative,
            label=fp.label,
            calculated_at=fp.calculated_at,
        )
    except Exception as exc:
        logger.error(f"Carbon footprint calculation failed for {sku}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Carbon calculation error: {exc}")


@router.get("/checkout/options", response_model=list[CheckoutOptionResponse])
async def get_checkout_options(
    sku: str = Query(..., description="Product SKU"),
    weight_kg: Optional[float] = Query(None, ge=0.001, description="Product weight in kg"),
    delivery_distance_km: Optional[float] = Query(None, ge=0.1, description="Delivery distance in km"),
):
    """
    Get **low-emission fulfillment alternatives** for display at checkout.

    Returns delivery options ranked by carbon impact (lowest first), allowing
    customers to make informed choices about their environmental impact.

    Example use: display a green badge on the Click & Collect option showing
    how much CO2 is saved versus standard home delivery.
    """
    if not isinstance(weight_kg, (int, float)):
        weight_kg = None
    if not isinstance(delivery_distance_km, (int, float)):
        delivery_distance_km = None
    try:
        options = _service.get_checkout_options(
            sku=sku,
            weight_kg=weight_kg,
            delivery_distance_km=delivery_distance_km,
        )
        return [CheckoutOptionResponse(**o.__dict__) for o in options]
    except Exception as exc:
        logger.error(f"Checkout options failed for {sku}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Checkout options error: {exc}")
