"""
Intent Service — Custom Model Wrapper
=======================================
Wraps the trained intent classifier to match the existing
IntentClassificationModule API signature.

Replaces LLM-based intent classification entirely.
"""

from typing import Tuple
from app.core.logger import logger
from app.ml_models.intent_classifier.model import intent_classifier


class IntentService:
    """
    Service layer wrapping the custom intent classifier.
    Returns the same (intent, confidence, complexity, needs_clarification)
    tuple expected by the LangGraph workflow.
    """

    async def classify(
        self,
        query: str,
        conversation_history: list = None,
        domain: str = "general",
    ) -> Tuple[str, float, str, bool]:
        """
        Classify user intent using the custom trained model.

        Returns:
            Tuple of (workflow_intent, confidence, complexity, needs_clarification)
        """
        # Quick greeting check
        clean_q = query.lower().strip().strip("!").strip(".")
        greetings = {
            "hi", "hello", "hey", "help", "good morning",
            "good afternoon", "hi there", "greetings",
            "thank you", "thanks", "goodbye", "bye",
        }
        if clean_q in greetings:
            logger.info(f"[IntentService] Greeting detected: '{query}' -> OFF_TOPIC")
            return ("OFF_TOPIC", 1.0, "Simple", True)

        # Use the custom model
        retail_intent, confidence, workflow_intent = intent_classifier.predict(query)

        # Determine complexity based on query length and keywords
        complexity = self._estimate_complexity(query)

        # Determine if clarification is needed
        needs_clarification = (workflow_intent == "OFF_TOPIC")

        logger.info(
            f"[IntentService] Custom model result: "
            f"retail={retail_intent}, workflow={workflow_intent}, "
            f"conf={confidence:.3f}, complexity={complexity}, "
            f"clarify={needs_clarification}"
        )

        return (workflow_intent, confidence, complexity, needs_clarification)

    def _estimate_complexity(self, query: str) -> str:
        """Estimate query complexity from text characteristics."""
        words = query.split()
        query_lower = query.lower()

        # Complex indicators
        complex_kw = ["compare", "trend", "correlation", "forecast",
                      "predict", "over time", "year over year",
                      "breakdown", "cross-reference", "and also"]
        if len(words) > 15 or any(kw in query_lower for kw in complex_kw):
            return "Complex"

        # Medium indicators
        medium_kw = ["by category", "by channel", "group by",
                     "filter", "between", "last month", "this week"]
        if len(words) > 8 or any(kw in query_lower for kw in medium_kw):
            return "Medium"

        return "Simple"

    def get_retail_intent(self, query: str) -> str:
        """Get the retail-specific intent label (not workflow label)."""
        retail_intent, _, _ = intent_classifier.predict(query)
        return retail_intent


# Singleton
intent_service = IntentService()
