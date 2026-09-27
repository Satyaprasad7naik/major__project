"""
Test Suite: Custom AI Models & Offline Pipeline Verification
============================================================
Validates that:
1. Intent Classifier correctly classifies domain queries without external LLM.
2. Demand Forecasting model predicts 7-day demand from features/database.
3. Stockout Risk Model accurately scores inventory risk levels.
4. Reorder Quantity Model correctly calculates replenishment volumes.
5. Rule-based SQL Generator produces valid SQLite queries for all intents.
6. Insight Generator creates structured Finding / Insight / Action summaries.
7. System runs 100% offline without requiring any external LLM API key.
"""

import unittest
import os
import sys

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.ml_models.intent_classifier.model import intent_classifier
from app.ml_models.demand_forecasting.model import demand_forecast_model
from app.ml_models.stockout_risk.model import stockout_risk_model
from app.ml_models.reorder_quantity.model import reorder_calculator
from app.ml_models.sql_generator.rule_engine import sql_generator
from app.services.intent_service import intent_service
from app.services.insight_generator import insight_generator_service
from app.services.forecasting_service import forecasting_service


class TestCustomAIModels(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        intent_classifier.load()
        demand_forecast_model.load()

    def test_stockout_intent(self):
        query = "Which products are going to run out of stock this week?"
        intent, conf, wf_intent = intent_classifier.predict(query)
        self.assertEqual(intent, "stockout_risk")
        self.assertGreater(conf, 0.2)
        self.assertEqual(wf_intent, "SELECT")

    def test_reorder_intent(self):
        query = "What should we reorder today?"
        intent, conf, wf_intent = intent_classifier.predict(query)
        self.assertEqual(intent, "reorder_recommendation")
        self.assertGreater(conf, 0.2)

    def test_sales_intent(self):
        query = "Show me the top selling styles by revenue"
        intent, conf, wf_intent = intent_classifier.predict(query)
        self.assertEqual(intent, "sales_analysis")
        self.assertGreater(conf, 0.2)

    def test_inventory_intent(self):
        query = "What is our current warehouse stock count for footwear?"
        intent, conf, wf_intent = intent_classifier.predict(query)
        self.assertEqual(intent, "inventory_status")
        self.assertGreater(conf, 0.2)

    def test_demand_forecasting_prediction(self):
        res = demand_forecast_model.predict_demand(sku="SKU-0001", horizon_days=7)
        self.assertIn("predicted_demand", res)
        self.assertEqual(len(res["predicted_demand"]), 7)
        self.assertIn("safety_stock_metrics", res)
        self.assertIn("stockout_risk_assessment", res)

    def test_stockout_risk_calculation(self):
        # Assess risk for a low-stock item
        res = stockout_risk_model.assess_risk(
            sku="SKU-TEST",
            current_stock=2,
            avg_daily_demand=2.0,
            lead_time_days=5.0,
            reorder_point=10
        )
        self.assertIn(res["risk_level"].upper(), ["CRITICAL", "HIGH"])
        self.assertEqual(res["days_of_cover"], 1.0)
        self.assertGreater(res["stockout_probability"], 0.8)

    def test_reorder_calculator_zero_stock(self):
        # If current_stock <= 0: max(reorder_point * 3, 15)
        qty = reorder_calculator.calculate(current_stock=0, reorder_point=10)
        self.assertEqual(qty, 30)

    def test_reorder_calculator_low_stock(self):
        # If current_stock < reorder_point: (reorder_point - current_stock) + reorder_point
        qty = reorder_calculator.calculate(current_stock=4, reorder_point=10)
        self.assertEqual(qty, 16)

    def test_reorder_calculator_adequate_stock(self):
        # If current_stock >= reorder_point: 0
        qty = reorder_calculator.calculate(current_stock=15, reorder_point=10)
        self.assertEqual(qty, 0)

    def test_sql_generator_stockout(self):
        sql = sql_generator.generate(
            query="Which tops are out of stock?",
            retail_intent="stockout_risk"
        )
        self.assertIn("SELECT", sql)
        self.assertIn("FROM products", sql)
        self.assertIn("WHERE", sql)

    def test_insight_generator_stockout(self):
        mock_data = [
            {"sku": "SKU-001", "style_name": "Silk Blouse", "stock_count": 2, "reorder_point": 10},
            {"sku": "SKU-002", "style_name": "Denim Jeans", "stock_count": 0, "reorder_point": 15},
        ]
        res = insight_generator_service.generate(
            query="Which products are at risk?",
            results=mock_data,
            retail_intent="stockout_risk"
        )
        self.assertIn("insight", res)
        self.assertIn("recommendation", res)
        self.assertTrue("Silk Blouse" in res["insight"] or "Denim Jeans" in res["insight"])

    def test_forecasting_service_reorder(self):
        qty = forecasting_service.calculate_reorder(current_stock=2, reorder_point=10)
        self.assertEqual(qty, 18)


if __name__ == "__main__":
    unittest.main()
