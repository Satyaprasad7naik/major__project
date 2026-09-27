"""
app/api/pricing_endpoints.py
=============================
Dynamic Pricing Engine API endpoints (Phase 2 of AGENTS.md roadmap).

Endpoints:
    GET  /api/v1/pricing/{sku}       — real-time price recommendation for one SKU
    POST /api/v1/pricing/batch       — batch pricing for a list of SKUs
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.dynamic_pricing import DynamicPricingEngine, BatchPriceRequest
from app.core.logger import logger

router = APIRouter(prefix="/api/v1/pricing", tags=["dynamic-pricing"])

_engine = DynamicPricingEngine()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic response schemas
# ─────────────────────────────────────────────────────────────────────────────

class PriceRecommendationResponse(BaseModel):
    sku: str
    base_price: float
    recommended_price: float
    discount_pct: float = Field(description="Negative = surcharge, Positive = discount")
    confidence: float = Field(ge=0.0, le=1.0)
    velocity_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    generated_at: str


class BatchPriceRequestBody(BaseModel):
    skus: list[str] = Field(..., min_length=1, max_length=100, description="List of SKU identifiers")
    override_base_prices: Optional[dict[str, float]] = Field(
        None,
        description="Optional map of sku -> base_price to override DB lookup",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{sku}", response_model=PriceRecommendationResponse)
async def get_price_recommendation(
    sku: str,
    base_price: Optional[float] = Query(
        None,
        description="Override base price. If omitted, the engine derives it from transaction history.",
        ge=0.01,
    ),
):
    """
    Get a real-time dynamic price recommendation for a single SKU.

    The engine considers:
    - **Inventory velocity**: transaction count in the last 24 hours
    - **Seasonal factors**: month-of-year demand multipliers
    - **Elasticity bounds**: max ±20% surcharge / ±30% discount

    Returns the recommended price with confidence score and full reasoning.
    """
    try:
        if not isinstance(base_price, (int, float)):
            base_price = None
        rec = _engine.get_price(sku=sku, base_price=base_price)
        return PriceRecommendationResponse(**rec.__dict__)
    except Exception as exc:
        logger.error(f"Pricing error for SKU {sku}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pricing engine error: {exc}")


@router.post("/batch", response_model=list[PriceRecommendationResponse])
async def get_batch_price_recommendations(body: BatchPriceRequestBody):
    """
    Get dynamic price recommendations for a batch of SKUs (max 100 per request).

    Useful for populating pricing badges on catalog grids or cart drawers.
    Failed individual SKUs return a zero-confidence entry rather than failing the whole batch.
    """
    try:
        request = BatchPriceRequest(
            skus=body.skus,
            override_base_prices=body.override_base_prices,
        )
        results = _engine.get_batch_prices(request)
        return [PriceRecommendationResponse(**r.__dict__) for r in results]
    except Exception as exc:
        logger.error(f"Batch pricing error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch pricing error: {exc}")
