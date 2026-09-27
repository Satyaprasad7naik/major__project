"""
Forecasting Service — Unified Demand + Risk + Reorder
======================================================
Wraps all predictive models behind a single service interface.
"""

from typing import Dict, Any, List
from app.core.logger import logger
from app.ml_models.demand_forecasting.model import demand_forecast_model
from app.ml_models.stockout_risk.model import stockout_risk_model
from app.ml_models.reorder_quantity.model import reorder_calculator


class ForecastingService:
    """
    Unified forecasting service combining demand prediction,
    stockout risk assessment, and reorder calculation.
    """

    def predict_demand(
        self,
        sku: str,
        horizon_days: int = 7,
        db_path: str = "retail_clothing.db",
    ) -> Dict[str, Any]:
        """Predict demand for a SKU."""
        logger.info(f"[ForecastingService] Demand prediction for {sku}, horizon={horizon_days}d")
        return demand_forecast_model.predict_demand(sku, horizon_days, db_path)

    def assess_stockout_risk(
        self,
        sku: str,
        current_stock: int,
        avg_daily_demand: float,
        lead_time_days: float,
        reorder_point: int,
        predicted_demand_7d: float = None,
    ) -> Dict[str, Any]:
        """Assess stockout risk for a single SKU."""
        return stockout_risk_model.assess_risk(
            sku=sku,
            current_stock=current_stock,
            avg_daily_demand=avg_daily_demand,
            lead_time_days=lead_time_days,
            reorder_point=reorder_point,
            predicted_demand_7d=predicted_demand_7d,
        )

    def calculate_reorder(
        self,
        current_stock: int,
        reorder_point: int,
        avg_daily_demand: float = 0,
        lead_time_days: float = 7,
    ) -> int:
        """Calculate reorder quantity."""
        return reorder_calculator.calculate(
            current_stock=current_stock,
            reorder_point=reorder_point,
            avg_daily_demand=avg_daily_demand,
            lead_time_days=lead_time_days,
        )

    def analyze_all_stockout_risks(
        self,
        db_path: str = "retail_clothing.db",
        threshold_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Analyze stockout risk for all products."""
        logger.info(f"[ForecastingService] Full stockout analysis, threshold={threshold_days}d")
        return stockout_risk_model.analyze_all_products(db_path, threshold_days)


# Singleton
forecasting_service = ForecastingService()
