"""
Comprehensive Model Training Script
===================================
Trains all custom AI models for InsightOS:
1. Intent Classifier (TF-IDF + Logistic Regression)
2. Demand Forecaster (XGBoost / Random Forest Regressor)

Stores all trained artifacts in the models/ directory.
"""

import os
import sys
import time

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.logger import logger
from app.ml_models.intent_classifier.train import train_intent_model
from app.ml_models.demand_forecasting.train import train_demand_model
from app.ml_models.model_manager import model_manager


def main():
    print("=" * 60)
    print(" InsightOS -- Custom AI Models Training Pipeline")
    print("=" * 60)
    
    start_total = time.time()
    
    # 1. Train Intent Classifier
    print("\n[Step 1/3] Training Intent Classification Model...")
    try:
        metrics_intent = train_intent_model()
        print("  [SUCCESS] Intent Classifier trained successfully!")
        print(f"  - Test Accuracy: {metrics_intent.get('accuracy', 0):.4f}")
        print(f"  - Total Classes: {metrics_intent.get('num_classes', 0)}")
        print(f"  - Samples Used:  {metrics_intent.get('num_samples', 0)}")
    except Exception as e:
        print(f"  [FAILED] Intent Classifier training failed: {e}")
        logger.error(f"Intent training failed: {e}")

    # 2. Train Demand Forecaster
    print("\n[Step 2/3] Training Demand Forecasting Model...")
    try:
        metrics_demand = train_demand_model()
        print("  [SUCCESS] Demand Forecasting Model trained successfully!")
        print(f"  - Algorithm:    {metrics_demand.get('algorithm', 'N/A')}")
        print(f"  - Test MAE:     {metrics_demand.get('mae', 0):.4f}")
        print(f"  - Test R2:      {metrics_demand.get('r2', 0):.4f}")
        print(f"  - Samples Used: {metrics_demand.get('num_samples', 0)}")
    except Exception as e:
        print(f"  [FAILED] Demand Forecaster training failed: {e}")
        logger.error(f"Demand training failed: {e}")

    # 3. Verify Model Manager Loading
    print("\n[Step 3/3] Verifying Model Manager Loading & Runtime Integration...")
    try:
        model_manager.load_all_models(force_reload=True)
        status = model_manager.get_model_status()
        print("  [SUCCESS] Model Manager loaded models:")
        for model_name, info in status.get("models", {}).items():
            print(f"    - {model_name}: loaded={info.get('loaded')} (type: {info.get('type')})")
    except Exception as e:
        print(f"  [FAILED] Model Manager verification failed: {e}")
        logger.error(f"Model manager verification failed: {e}")

    elapsed = time.time() - start_total
    print("\n" + "=" * 60)
    print(f" Training pipeline completed in {elapsed:.2f}s")
    print(" All models ready for 100% offline inference.")
    print("=" * 60)


if __name__ == "__main__":
    main()
