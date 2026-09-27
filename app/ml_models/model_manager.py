"""
Model Manager — Central Model Lifecycle Controller
====================================================
Loads all custom AI models at application startup and provides
a unified accessor for runtime components.

Usage:
    from app.ml_models.model_manager import model_manager
    model_manager.load_all()
    intent = model_manager.get_model("intent_classifier")
"""

import time
from typing import Dict, Any, Optional
from app.core.logger import logger


class ModelManager:
    """
    Manages loading, versioning, and access for all custom ML models.
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._load_times: Dict[str, float] = {}
        self._initialized = False

    def load_all(self) -> Dict[str, bool]:
        """
        Load all custom models at startup.

        Returns:
            Dict mapping model name → load success status
        """
        logger.info("=" * 60)
        logger.info("[ModelManager] Loading custom AI models...")
        logger.info("=" * 60)

        results = {}
        total_start = time.time()

        # 1. Intent Classifier
        start = time.time()
        try:
            from app.ml_models.intent_classifier.model import intent_classifier
            success = intent_classifier.load()
            self._models["intent_classifier"] = intent_classifier
            results["intent_classifier"] = success
            self._load_times["intent_classifier"] = time.time() - start
            status = "[LOADED]" if success else "[FALLBACK]"
            logger.info(f"  [1/4] Intent Classifier: {status} ({self._load_times['intent_classifier']:.2f}s)")
        except Exception as e:
            results["intent_classifier"] = False
            logger.error(f"  [1/4] Intent Classifier: [ERROR] {e}")

        # 2. Demand Forecasting
        start = time.time()
        try:
            from app.ml_models.demand_forecasting.model import demand_forecast_model
            success = demand_forecast_model.load()
            self._models["demand_forecasting"] = demand_forecast_model
            results["demand_forecasting"] = success
            self._load_times["demand_forecasting"] = time.time() - start
            status = "[LOADED]" if success else "[FALLBACK]"
            logger.info(f"  [2/4] Demand Forecasting: {status} ({self._load_times['demand_forecasting']:.2f}s)")
        except Exception as e:
            results["demand_forecasting"] = False
            logger.error(f"  [2/4] Demand Forecasting: [ERROR] {e}")

        # 3. Stockout Risk (no trained model needed — hybrid rule engine)
        start = time.time()
        try:
            from app.ml_models.stockout_risk.model import stockout_risk_model
            self._models["stockout_risk"] = stockout_risk_model
            results["stockout_risk"] = True
            self._load_times["stockout_risk"] = time.time() - start
            logger.info(f"  [3/4] Stockout Risk: [READY] ({self._load_times['stockout_risk']:.2f}s)")
        except Exception as e:
            results["stockout_risk"] = False
            logger.error(f"  [3/4] Stockout Risk: [ERROR] {e}")

        # 4. Reorder Quantity (rule-based, always available)
        start = time.time()
        try:
            from app.ml_models.reorder_quantity.model import reorder_calculator
            self._models["reorder_quantity"] = reorder_calculator
            results["reorder_quantity"] = True
            self._load_times["reorder_quantity"] = time.time() - start
            logger.info(f"  [4/4] Reorder Quantity: [READY] ({self._load_times['reorder_quantity']:.2f}s)")
        except Exception as e:
            results["reorder_quantity"] = False
            logger.error(f"  [4/4] Reorder Quantity: [ERROR] {e}")

        total_time = time.time() - total_start
        loaded = sum(1 for v in results.values() if v)
        total = len(results)

        logger.info("=" * 60)
        logger.info(
            f"[ModelManager] {loaded}/{total} models loaded in {total_time:.2f}s"
        )
        logger.info(
            "[ModelManager] System operating WITHOUT external LLM — "
            "all predictions are from custom models"
        )
        logger.info("=" * 60)

        self._initialized = True
        return results

    def get_model(self, name: str) -> Optional[Any]:
        """Get a loaded model by name."""
        model = self._models.get(name)
        if model is None:
            logger.warning(f"[ModelManager] Model '{name}' not found. Available: {list(self._models.keys())}")
        return model

    def get_status(self) -> Dict[str, Any]:
        """Get status of all models."""
        return {
            "initialized": self._initialized,
            "models": {
                name: {
                    "loaded": name in self._models,
                    "load_time_s": round(self._load_times.get(name, 0), 3),
                    "type": type(model).__name__ if (model := self._models.get(name)) else "N/A",
                }
                for name in ["intent_classifier", "demand_forecasting", "stockout_risk", "reorder_quantity"]
            },
            "provider": "custom_trained_models",
            "external_llm_required": False,
        }

    def load_all_models(self, force_reload: bool = False) -> Dict[str, bool]:
        """Alias for load_all."""
        return self.load_all()

    def get_model_status(self) -> Dict[str, Any]:
        """Alias for get_status."""
        return self.get_status()

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# Singleton
model_manager = ModelManager()
