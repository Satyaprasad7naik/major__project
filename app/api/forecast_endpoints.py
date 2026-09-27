"""
Demand Forecasting API Endpoints for InsightOS.
Endpoints specified in AUTO_INSIGHTS_FEATURE.md:
- GET /api/v1/forecast/{sku_id}?horizon=14
- POST /api/v1/forecast/batch
"""

from fastapi import APIRouter, HTTPException, Query, Path, Body
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.modules.demand_forecaster import DemandForecaster
from app.services.auto_insights import get_db_connection
from app.core.logger import logger

router = APIRouter(prefix="/forecast", tags=["forecast"])


class BatchForecastRequest(BaseModel):
    sku_ids: Optional[List[str]] = Field(None, description="Specific SKUs to forecast (or all if omitted)")
    horizon_days: Optional[int] = Field(14, ge=1, le=60, description="Forecast horizon in days")
    db_path: Optional[str] = Field("retail_clothing.db", description="Database file path")


@router.get("/{sku_id}", response_model=dict)
async def get_sku_forecast(
    sku_id: str = Path(..., description="Product SKU identifier (e.g., SKU-1001)"),
    horizon: int = Query(14, ge=1, le=60, description="Forecast horizon in days"),
    db_path: str = Query("retail_clothing.db", description="Database file path")
):
    """
    Returns multi-step CNN-LSTM sales demand forecast, 95% confidence intervals,
    and mathematically grounded dynamic safety stock metrics for a given SKU.
    """
    clean_horizon = horizon if isinstance(horizon, int) else 14
    clean_db = db_path if isinstance(db_path, str) else "retail_clothing.db"
    try:
        forecast_result = DemandForecaster.generate_sku_forecast(
            sku_id=sku_id,
            horizon_days=clean_horizon,
            db_path=clean_db
        )
        return {
            "status": "success",
            "data": forecast_result
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        logger.error(f"Demand forecast failed for {sku_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/batch", response_model=dict)
async def batch_forecast(payload: Optional[BatchForecastRequest] = Body(None)):
    """
    Recalculates stockout probabilities and dynamic safety stock thresholds
    across active inventory items.
    """
    horizon = payload.horizon_days if (payload and hasattr(payload, "horizon_days") and payload.horizon_days) else 14
    db_file = payload.db_path if (payload and hasattr(payload, "db_path") and payload.db_path) else "retail_clothing.db"
    sku_list = payload.sku_ids if (payload and hasattr(payload, "sku_ids") and payload.sku_ids) else None
    
    conn = None
    try:
        conn = get_db_connection(db_file)
        cursor = conn.cursor()
        
        if not sku_list:
            rows = cursor.execute("SELECT sku FROM products LIMIT 10;").fetchall()
            sku_list = [r["sku"] for r in rows]
            
        results = []
        for sku in sku_list:
            try:
                res = DemandForecaster.generate_sku_forecast(sku, horizon_days=horizon, db_path=db_file)
                results.append(res)
            except Exception as e:
                logger.warning(f"Batch forecast skipped for {sku}: {e}")
                
        return {
            "status": "success",
            "count": len(results),
            "forecasts": results
        }
    except Exception as exc:
        logger.error(f"Batch forecast failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()
