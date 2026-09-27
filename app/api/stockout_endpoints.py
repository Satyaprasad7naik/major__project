"""Stockout Risk API Endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.modules.stockout_analyzer import analyze_stockout_risk
from app.core.logger import logger

router = APIRouter(prefix="/stockout", tags=["stockout"])

@router.get("/risk")
async def get_stockout_risk(
    domain: str = Query("retail_clothing", description="Domain to analyze"),
    days: int = Query(7, ge=1, le=90, description="Days ahead threshold"),
    method: str = Query("auto", description="Calculation method: simple, days_of_cover, auto"),
):
    """Get products at risk of stockout."""
    logger.info(f"Stockout risk request: domain={domain}, days={days}, method={method}")

    try:
        results = analyze_stockout_risk(domain, threshold_days=days, method=method)
        return {
            "domain": domain,
            "threshold_days": days,
            "method": method,
            "count": len(results),
            "at_risk_products": results
        }
    except Exception as e:
        logger.error(f"Stockout risk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sku/{sku}")
async def get_stockout_detail(
    sku: str,
    domain: str = Query("retail_clothing", description="Domain"),
):
    """Get detailed stockout analysis for a specific SKU."""
    logger.info(f"Stockout detail request: sku={sku}, domain={domain}")

    try:
        results = analyze_stockout_risk(domain, threshold_days=90, method="auto")
        product = next((r for r in results if r['sku'] == sku), None)

        if not product:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found or not at risk")

        return product
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stockout detail failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))