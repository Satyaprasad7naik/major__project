"""
Demand Forecasting Model — Training Script
============================================
Trains an XGBoost Regressor on historical sales data from retail_clothing.db.
Produces: demand_model.pkl

Features: day_of_week, month, current_stock, avg_sales_7d, avg_sales_14d, avg_sales_30d
Target: units_sold (next period demand)
"""

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

from sklearn.ensemble import RandomForestRegressor


def load_sales_data(db_path: str = "retail_clothing.db") -> pd.DataFrame:
    """Load and prepare sales data from database."""
    conn = sqlite3.connect(db_path)

    # Get sales events with product info
    query = """
        SELECT
            se.sku,
            se.units_sold,
            se.sale_date,
            se.channel,
            p.category,
            p.unit_cost,
            p.retail_price,
            i.stock_count,
            i.reorder_point
        FROM sales_events se
        JOIN products p ON se.sku = p.sku
        LEFT JOIN inventory i ON se.sku = i.sku
        ORDER BY se.sale_date
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create ML features from raw sales data."""
    df = df.copy()

    # Parse date
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    df = df.dropna(subset=["sale_date"])

    # Calendar features
    df["day_of_week"] = df["sale_date"].dt.dayofweek
    df["month"] = df["sale_date"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Sort by SKU and date for rolling calculations
    df = df.sort_values(["sku", "sale_date"]).reset_index(drop=True)

    # Rolling average sales per SKU
    for window in [7, 14, 30]:
        col_name = f"avg_sales_{window}d"
        df[col_name] = (
            df.groupby("sku")["units_sold"]
            .transform(lambda x: x.rolling(window, min_periods=1).mean())
        )

    # Price ratio (unit cost / retail price)
    df["price_ratio"] = np.where(
        df["retail_price"] > 0,
        df["unit_cost"] / df["retail_price"],
        0.5
    )

    # Stock level (current_stock / reorder_point)
    df["stock_ratio"] = np.where(
        df["reorder_point"] > 0,
        df["stock_count"] / df["reorder_point"],
        1.0
    )

    # Fill NaNs
    df = df.fillna(0)

    return df


FEATURE_COLUMNS = [
    "day_of_week",
    "month",
    "is_weekend",
    "stock_count",
    "reorder_point",
    "avg_sales_7d",
    "avg_sales_14d",
    "avg_sales_30d",
    "price_ratio",
    "stock_ratio",
    "unit_cost",
    "retail_price",
]


def train_demand_model(db_path: str = "retail_clothing.db", save_dir: str = None):
    """
    Train and save the Demand Forecasting model.

    Returns:
        dict with MAE, RMSE, R², and model path
    """
    if save_dir is None:
        save_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(save_dir, exist_ok=True)

    print("[Demand Forecaster] Loading sales data...")
    df = load_sales_data(db_path)
    print(f"[Demand Forecaster] Raw records: {len(df)}")

    if len(df) < 10:
        print("[Demand Forecaster] [WARN] Insufficient sales data. Generating synthetic training data...")
        df = _generate_synthetic_data()

    print("[Demand Forecaster] Engineering features...")
    df = engineer_features(df)

    # Prepare X, y
    available_features = [f for f in FEATURE_COLUMNS if f in df.columns]
    X = df[available_features].values
    y = df["units_sold"].values.astype(float)

    print(f"[Demand Forecaster] Features: {available_features}")
    print(f"[Demand Forecaster] Training samples: {len(X)}")

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Train model (XGBoost preferred, RandomForest fallback)
    if HAS_XGBOOST:
        print("[Demand Forecaster] Training XGBoost Regressor...")
        model = XGBRegressor(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            objective="reg:squarederror",
        )
    else:
        print("[Demand Forecaster] XGBoost not available. Training RandomForest Regressor...")
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            random_state=42,
        )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print(f"\n[Demand Forecaster] Test MAE:  {mae:.4f}")
    print(f"[Demand Forecaster] Test RMSE: {rmse:.4f}")
    print(f"[Demand Forecaster] Test R2:   {r2:.4f}")

    # Feature importance
    if HAS_XGBOOST:
        importances = model.feature_importances_
    else:
        importances = model.feature_importances_

    print("\n[Demand Forecaster] Feature Importance:")
    for feat, imp in sorted(zip(available_features, importances), key=lambda x: -x[1]):
        print(f"  {feat}: {imp:.4f}")

    # Save
    model_path = os.path.join(save_dir, "demand_model.pkl")
    meta_path = os.path.join(save_dir, "model_meta.pkl")

    joblib.dump(model, model_path)
    joblib.dump({
        "feature_columns": available_features,
        "algorithm": "xgboost" if HAS_XGBOOST else "random_forest",
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "trained_at": datetime.now().isoformat(),
    }, meta_path)

    print(f"\n[Demand Forecaster] Model saved to: {model_path}")

    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "model_path": model_path,
        "num_samples": len(X),
        "features": available_features,
    }


def _generate_synthetic_data() -> pd.DataFrame:
    """Generate synthetic training data if DB has insufficient records."""
    np.random.seed(42)
    skus = [f"SKU-{i:04d}" for i in range(1001, 1021)]
    rows = []

    base_date = datetime.now() - timedelta(days=90)
    for sku in skus:
        base_demand = np.random.uniform(2, 15)
        stock = np.random.randint(5, 100)
        reorder = np.random.randint(10, 30)
        unit_cost = np.random.uniform(20, 80)
        retail_price = unit_cost * np.random.uniform(1.5, 3.0)
        category = np.random.choice(["Tops", "Bottoms", "Footwear", "Accessories"])

        for day_offset in range(90):
            date = base_date + timedelta(days=day_offset)
            weekday = date.weekday()
            seasonal = 1.3 if weekday >= 5 else 1.0
            demand = max(1, int(base_demand * seasonal + np.random.normal(0, 2)))

            rows.append({
                "sku": sku,
                "units_sold": demand,
                "sale_date": date.strftime("%Y-%m-%d"),
                "channel": np.random.choice(["ONLINE", "STORE"]),
                "category": category,
                "unit_cost": unit_cost,
                "retail_price": retail_price,
                "stock_count": stock,
                "reorder_point": reorder,
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    result = train_demand_model()
    print(f"\n[SUCCESS] Training complete. MAE: {result['mae']:.2f}, R2: {result['r2']:.2%}")
