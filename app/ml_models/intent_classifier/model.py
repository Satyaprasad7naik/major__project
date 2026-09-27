"""
Intent Classification Model — Runtime Predictor
=================================================
Loads the trained TF-IDF + Logistic Regression model and predicts
intent labels with confidence scores for incoming user queries.

Falls back to keyword-based matching if model files are not found.
"""

import os
import re
import joblib
from typing import Tuple, Optional
from app.core.logger import logger


# Intent label mapping to workflow-compatible values
_INTENT_MAP = {
    "stockout_risk": "SELECT",
    "reorder_recommendation": "SELECT",
    "sales_analysis": "SELECT",
    "inventory_status": "SELECT",
    "general_query": "SELECT",
    "schema_query": "SELECT",
    "login_events": "SELECT",
    "users_query": "SELECT",
    "transactions_query": "SELECT",
    "alerts_query": "SELECT",
    "off_topic": "OFF_TOPIC",
}


class IntentClassifierModel:
    """
    Custom-trained Intent Classifier using TF-IDF + Logistic Regression.
    Replaces the external LLM-based intent classification.
    """

    def __init__(self):
        self.model = None
        self.vectorizer = None
        self.loaded = False
        self._model_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__))
        )

    def load(self) -> bool:
        """Load the trained model and vectorizer from disk."""
        model_path = os.path.join(self._model_dir, "intent_model.pkl")
        vectorizer_path = os.path.join(self._model_dir, "tfidf_vectorizer.pkl")

        if not os.path.exists(model_path) or not os.path.exists(vectorizer_path):
            logger.warning(
                f"[IntentClassifier] Model files not found at {self._model_dir}. "
                "Using keyword fallback. Run 'python scripts/train_all_models.py' to train."
            )
            return False

        try:
            self.model = joblib.load(model_path)
            self.vectorizer = joblib.load(vectorizer_path)
            self.loaded = True
            logger.info("[IntentClassifier] [LOADED] Custom model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"[IntentClassifier] Failed to load model: {e}")
            return False

    def predict(self, text: str) -> Tuple[str, float, str]:
        """
        Predict intent from user text.

        Returns:
            Tuple of (retail_intent, confidence, workflow_intent)
            e.g. ("stockout_risk", 0.92, "SELECT")
        """
        if self.loaded and self.model is not None:
            return self._predict_ml(text)
        else:
            return self._predict_keyword(text)

    def _predict_ml(self, text: str) -> Tuple[str, float, str]:
        """ML-based prediction using the trained model."""
        text_lower = text.lower().strip()
        
        # Explicit greeting check
        greetings = {"hi", "hello", "hey", "help", "good morning",
                     "good afternoon", "hi there", "greetings",
                     "thank you", "thanks", "goodbye", "bye"}
        if text_lower.strip("!.") in greetings:
            return "off_topic", 1.0, "OFF_TOPIC"

        # Retail domain indicator keywords
        retail_keywords = [
            "stock", "reorder", "product", "item", "sku", "sales", "revenue",
            "sell", "sold", "supplier", "vendor", "inventory", "category", "price",
            "cost", "order", "purchase", "warehouse", "catalog", "lead time",
            "headphones", "keyboard", "tumbler", "t-shirt", "watch", "candle",
            "backpack", "wallet", "socks"
        ]
        has_retail_kw = any(kw in text_lower for kw in retail_keywords)

        # Database / Security / Query keywords
        data_keywords = [
            "login", "logins", "failed", "attempt", "attempts", "email", "emails",
            "user", "users", "transaction", "transactions", "alert", "alerts",
            "audit", "log", "logs", "schema", "table", "tables", "column", "columns",
            "show", "list", "select", "find", "get", "display", "all", "what", "which",
            "count", "how many", "who", "record", "records", "status"
        ]
        has_data_kw = any(kw in text_lower for kw in data_keywords)

        X = self.vectorizer.transform([text])
        proba = self.model.predict_proba(X)[0]
        predicted_idx = proba.argmax()
        confidence = float(proba[predicted_idx])
        retail_intent = self.model.classes_[predicted_idx]

        # Prevent false off-topic classifications for queries with retail or data query keywords
        if (retail_intent == "off_topic" or confidence < 0.40) and (has_retail_kw or has_data_kw):
            if any(k in text_lower for k in ["login", "failed", "attempt"]):
                retail_intent = "login_events"
            elif any(k in text_lower for k in ["user", "kyc", "pep", "profile"]):
                retail_intent = "users_query"
            elif any(k in text_lower for k in ["transaction", "payment", "trade", "deposit", "withdraw"]):
                retail_intent = "transactions_query"
            elif any(k in text_lower for k in ["alert", "rule"]):
                retail_intent = "alerts_query"
            elif any(k in text_lower for k in ["stockout", "risk", "running low", "low stock", "run out"]):
                retail_intent = "stockout_risk"
            elif any(k in text_lower for k in ["reorder", "restock", "buy", "purchase order", "how many", "should we order"]):
                retail_intent = "reorder_recommendation"
            elif any(k in text_lower for k in ["sales", "revenue", "sold", "top selling", "best selling"]):
                retail_intent = "sales_analysis"
            elif any(k in text_lower for k in ["inventory", "warehouse", "catalog", "products", "items", "categories"]):
                retail_intent = "inventory_status"
            elif any(k in text_lower for k in ["schema", "table", "structure"]):
                retail_intent = "schema_query"
            else:
                retail_intent = "general_query"
            confidence = 0.90

        workflow_intent = _INTENT_MAP.get(retail_intent, "SELECT")

        logger.info(
            f"[IntentClassifier] ML prediction: {retail_intent} "
            f"(conf: {confidence:.3f}) -> workflow: {workflow_intent}"
        )
        return retail_intent, confidence, workflow_intent

    def _predict_keyword(self, text: str) -> Tuple[str, float, str]:
        """Keyword-based fallback when model is not loaded."""
        text_lower = text.lower().strip()

        # Greetings / off-topic
        greetings = {"hi", "hello", "hey", "help", "good morning",
                      "good afternoon", "hi there", "greetings",
                      "thank you", "goodbye", "bye"}
        if text_lower.strip("!.") in greetings:
            return "off_topic", 1.0, "OFF_TOPIC"

        # Schema queries
        schema_kw = ["schema", "tables", "columns", "database structure",
                     "what can i ask", "what tables", "describe"]
        if any(kw in text_lower for kw in schema_kw):
            return "schema_query", 0.85, "SELECT"

        # Login events & security
        if any(kw in text_lower for kw in ["login", "failed", "attempt", "auth"]):
            return "login_events", 0.90, "SELECT"

        # Users & profiles
        if any(kw in text_lower for kw in ["user", "users", "kyc", "pep", "account status"]):
            return "users_query", 0.90, "SELECT"

        # Transactions
        if any(kw in text_lower for kw in ["transaction", "payment", "trade", "deposit", "withdraw"]):
            return "transactions_query", 0.90, "SELECT"

        # Alerts
        if any(kw in text_lower for kw in ["alert", "alerts", "rule"]):
            return "alerts_query", 0.90, "SELECT"

        # Stockout risk
        stockout_kw = ["stockout", "out of stock", "running low", "low stock",
                       "run out", "critical", "below reorder", "risk",
                       "days of cover", "zero stock"]
        if any(kw in text_lower for kw in stockout_kw):
            return "stockout_risk", 0.85, "SELECT"

        # Reorder
        reorder_kw = ["reorder", "purchase order", "how much.*order",
                      "restocking", "replenishment", "buy", "draft po",
                      "restock", "order quantity"]
        if any(re.search(kw, text_lower) for kw in reorder_kw):
            return "reorder_recommendation", 0.80, "SELECT"

        # Sales analysis
        sales_kw = ["sales", "revenue", "sold", "top selling",
                    "best selling", "performance", "units sold",
                    "trending", "slow moving"]
        if any(kw in text_lower for kw in sales_kw):
            return "sales_analysis", 0.85, "SELECT"

        # Inventory status
        inventory_kw = ["inventory", "stock count", "stock level",
                        "how much stock", "warehouse", "in stock",
                        "available", "catalog", "products",
                        "current stock", "list all"]
        if any(kw in text_lower for kw in inventory_kw):
            return "inventory_status", 0.80, "SELECT"

        # Supplier / general
        general_kw = ["supplier", "lead time", "sync", "import",
                      "summary", "overview", "report", "dashboard"]
        if any(kw in text_lower for kw in general_kw):
            return "general_query", 0.75, "SELECT"

        # Default: general query
        return "general_query", 0.60, "SELECT"

    def get_detailed_prediction(self, text: str) -> dict:
        """
        Returns full prediction details including all class probabilities.
        Useful for debugging and model explainability.
        """
        retail_intent, confidence, workflow_intent = self.predict(text)

        result = {
            "input_text": text,
            "retail_intent": retail_intent,
            "workflow_intent": workflow_intent,
            "confidence": round(confidence, 4),
            "model_used": "tfidf_logistic_regression" if self.loaded else "keyword_fallback",
        }

        # Add all class probabilities if ML model is loaded
        if self.loaded and self.model is not None:
            X = self.vectorizer.transform([text])
            proba = self.model.predict_proba(X)[0]
            result["all_probabilities"] = {
                cls: round(float(p), 4)
                for cls, p in zip(self.model.classes_, proba)
            }

        return result


# Singleton instance
intent_classifier = IntentClassifierModel()
