"""
Demand Forecasting Model — Runtime Predictor
==============================================
Loads the trained XGBoost/RandomForest model and predicts
future demand for given SKU feature vectors.

Falls back to rolling average calculation if model is not found.
"""

import os
import math
import joblib
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sqlite3

from app.core.logger import logger


class DemandForecastModel:
    """
    Custom-trained demand forecasting model.
    Replaces the simulated CNN-LSTM forecaster.
    """

    def __init__(self):
        self.model = None
        self.meta = None
        self.loaded = False
        self._model_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> bool:
        """Load the trained model from disk."""
        model_path = os.path.join(self._model_dir, "demand_model.pkl")
        meta_path = os.path.join(self._model_dir, "model_meta.pkl")

        if not os.path.exists(model_path):
            logger.warning(
                f"[DemandForecast] Model not found at {model_path}. "
                "Using rolling average fallback. Run 'python scripts/train_all_models.py'."
            )
            return False

        try:
            self.model = joblib.load(model_path)
            if os.path.exists(meta_path):
                self.meta = joblib.load(meta_path)
            self.loaded = True
            algo = self.meta.get("algorithm", "unknown") if self.meta else "unknown"
            logger.info(f"[DemandForecast] [LOADED] Model loaded ({algo})")
            return True
        except Exception as e:
            logger.error(f"[DemandForecast] Failed to load model: {e}")
            return False

    def predict_demand(
        self,
        sku: str,
        horizon_days: int = 7,
        db_path: str = "retail_clothing.db",
    ) -> Dict[str, Any]:
        """
        Predict demand for a SKU over the next horizon_days.

        Returns full forecast result compatible with existing API.
        """
        # Gather SKU features from database
        sku_data = self._get_sku_data(sku, db_path)

        if self.loaded and self.model is not None:
            predictions = self._predict_ml(sku_data, horizon_days)
            model_name = self.meta.get("algorithm", "custom_ml") if self.meta else "custom_ml"
        else:
            predictions = self._predict_rolling_avg(sku_data, horizon_days)
            model_name = "rolling_average_fallback"

        # Build forecast output
        today = datetime.now()
        forecast_dates = [
            (today + timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(1, horizon_days + 1)
        ]

        # Confidence intervals (±1.96σ for 95% CI)
        std_dev = float(np.std(predictions)) if len(predictions) > 1 else 1.5
        upper = [round(max(p + 1.96 * std_dev, 0), 1) for p in predictions]
        lower = [round(max(p - 1.96 * std_dev, 0), 1) for p in predictions]

        # Dynamic safety stock
        avg_daily = float(np.mean(predictions)) if predictions else 3.0
        lead_time = float(sku_data.get("lead_time_days", 7))
        safety_stock = self._calculate_safety_stock(avg_daily, lead_time, std_dev)

        current_stock = int(sku_data.get("stock_count", 0))
        cumulative = sum(predictions[:int(lead_time)])
        projected = current_stock - cumulative

        if projected <= safety_stock["safety_stock_units"]:
            risk_level = "HIGH"
        elif projected <= safety_stock["reorder_point_units"]:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "sku_id": sku,
            "product_name": sku_data.get("style_name", f"Product {sku}"),
            "category": sku_data.get("category", "Apparel"),
            "current_stock": current_stock,
            "model_architecture": f"Custom {model_name.replace('_', ' ').title()} Model",
            "horizon_days": horizon_days,
            "forecast_dates": forecast_dates,
            "predicted_demand": [round(p, 1) for p in predictions],
            "confidence_upper_95": upper,
            "confidence_lower_95": lower,
            "safety_stock_metrics": safety_stock,
            "stockout_risk_assessment": {
                "risk_level": risk_level,
                "projected_balance_at_lead_time": round(projected, 1),
                "action_recommended": (
                    f"Initiate replenishment of {int(safety_stock['reorder_point_units'])} units immediately."
                    if risk_level in ("HIGH", "MEDIUM")
                    else "Inventory levels sufficient."
                ),
            },
        }

    def _predict_ml(self, sku_data: dict, horizon_days: int) -> List[float]:
        """Use trained ML model for predictions."""
        features = self.meta.get("feature_columns", []) if self.meta else []
        predictions = []

        today = datetime.now()
        for h in range(1, horizon_days + 1):
            future_date = today + timedelta(days=h)

            feature_vec = []
            for col in features:
                if col == "day_of_week":
                    feature_vec.append(future_date.weekday())
                elif col == "month":
                    feature_vec.append(future_date.month)
                elif col == "is_weekend":
                    feature_vec.append(1 if future_date.weekday() >= 5 else 0)
                elif col in sku_data:
                    feature_vec.append(float(sku_data.get(col, 0)))
                else:
                    feature_vec.append(0)

            pred = float(self.model.predict([feature_vec])[0])
            predictions.append(max(pred, 0.5))

        return predictions

    def _predict_rolling_avg(self, sku_data: dict, horizon_days: int) -> List[float]:
        """Fallback: rolling average with weekly seasonality."""
        avg_7d = float(sku_data.get("avg_sales_7d", 3.0))
        avg_30d = float(sku_data.get("avg_sales_30d", avg_7d))
        baseline = (avg_7d * 0.6 + avg_30d * 0.4)

        predictions = []
        today = datetime.now()
        for h in range(1, horizon_days + 1):
            future = today + timedelta(days=h)
            seasonal = 1.3 if future.weekday() >= 5 else 1.0
            trend = 1.0 + (0.005 * h)
            pred = max(baseline * seasonal * trend, 0.5)
            predictions.append(round(pred, 1))

        return predictions

    def _get_sku_data(self, sku: str, db_path: str) -> dict:
        """Fetch SKU features from database."""
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            row = cursor.execute("""
                SELECT p.sku, p.style_name, p.category, p.unit_cost, p.retail_price,
                       i.stock_count, i.reorder_point,
                       s.lead_time_days
                FROM products p
                LEFT JOIN inventory i ON p.sku = i.sku
                LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
                WHERE p.sku = ?
            """, (sku,)).fetchone()

            if row:
                data = dict(row)
            else:
                data = {"sku": sku, "style_name": f"Product {sku}",
                        "category": "Apparel", "stock_count": 5,
                        "reorder_point": 15, "lead_time_days": 7,
                        "unit_cost": 45.0, "retail_price": 89.0}

            # Get rolling averages from sales
            for window in [7, 14, 30]:
                cutoff = (datetime.now() - timedelta(days=window)).strftime("%Y-%m-%d")
                sales_row = cursor.execute("""
                    SELECT COALESCE(SUM(units_sold), 0) / ? as avg_sales
                    FROM sales_events
                    WHERE sku = ? AND sale_date >= ?
                """, (window, sku, cutoff)).fetchone()
                data[f"avg_sales_{window}d"] = float(sales_row["avg_sales"]) if sales_row else 0

            # Derived features
            data["price_ratio"] = (
                data.get("unit_cost", 45) / data.get("retail_price", 89)
                if data.get("retail_price", 0) > 0 else 0.5
            )
            data["stock_ratio"] = (
                data.get("stock_count", 0) / data.get("reorder_point", 15)
                if data.get("reorder_point", 0) > 0 else 1.0
            )

            conn.close()
            return data
        except Exception as e:
            logger.warning(f"[DemandForecast] DB lookup failed for {sku}: {e}")
            return {"sku": sku, "style_name": f"Product {sku}",
                    "category": "Apparel", "stock_count": 5,
                    "reorder_point": 15, "lead_time_days": 7,
                    "unit_cost": 45.0, "retail_price": 89.0,
                    "avg_sales_7d": 3.0, "avg_sales_14d": 3.0,
                    "avg_sales_30d": 3.0, "price_ratio": 0.5,
                    "stock_ratio": 0.33}

    @staticmethod
    def _calculate_safety_stock(
        daily_demand: float,
        lead_time: float,
        demand_std: float,
        z: float = 1.65,
    ) -> dict:
        """
        Safety Stock = Z * sqrt(L * σ_D² + D² * σ_L²)
        """
        L = max(lead_time, 1.0)
        sigma_L = 1.2  # lead time variability
        sigma_D = max(demand_std, 0.5)
        D = max(daily_demand, 0.1)

        variance = (L * sigma_D**2) + (D**2 * sigma_L**2)
        safety = z * math.sqrt(variance)
        reorder = (D * L) + safety

        return {
            "safety_stock_units": round(safety, 1),
            "reorder_point_units": round(reorder, 1),
            "service_level": "95%",
            "lead_time_days": L,
            "avg_daily_demand": round(D, 2),
            "demand_std_dev": round(sigma_D, 2),
        }


# Singleton instance
demand_forecast_model = DemandForecastModel()
demand_forecaster = demand_forecast_model
