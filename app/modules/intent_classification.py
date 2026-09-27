from typing import Dict, Any, Tuple
from app.core.logger import logger
from app.core.config import settings

class IntentClassificationModule:
    """
    HLD 3.3: Intent Classification Module
    Determines query type, complexity, confidence level, and if clarification is needed.
    Uses custom trained ML intent classifier (TF-IDF + Logistic Regression) without external LLMs.
    """
    
    async def classify(self, query: str, conversation_history: list = None, domain: str = "general") -> Tuple[str, float, str, bool]:
        """
        Returns (intent, confidence, complexity, needs_clarification)
        """
        if settings.USE_CUSTOM_MODELS:
            from app.services.intent_service import intent_service
            logger.info(f"[IntentModule] Using Custom ML Intent Classifier for query: '{query}'")
            return await intent_service.classify(query, conversation_history, domain)

        # Fallback to LLM if explicitly enabled
        clean_q = query.lower().strip().strip("!").strip(".")
        greetings = {"hi", "hello", "hey", "help", "good morning", "good afternoon", "hi there", "greetings"}
        if clean_q in greetings:
            return ("OFF_TOPIC", 1.0, "SIMPLE", True)

        logger.info(f"Classifying intent with LLM for domain: {domain} | Query: {query}")
        from app.services.llm import llm_service
        from app.core.resilient_llm import call_llm_structured
        from app.core.llm_schemas import IntentClassification, SAFE_FALLBACK_INTENT
        
        prompt = f"""You are an AI assistant for a Database system.
User Query: "{query}"
Analyze the query and return a valid JSON with intent, confidence, complexity, needs_clarification."""
        
        try:
            result = await call_llm_structured(
                prompt=prompt,
                schema=IntentClassification,
                llm_call_fn=llm_service.generate_response,
                fallback=SAFE_FALLBACK_INTENT,
                model_name=settings.INTENT_MODEL,
            )
            intent = result.intent
            confidence = result.confidence
            complexity = result.complexity
            needs_clarification = result.needs_clarification
            if intent == "SELECT":
                needs_clarification = False
            return intent, confidence, complexity, needs_clarification
        except Exception as e:
            logger.error(f"Intent classification error: {str(e)}")
            return "SELECT", 0.9, "Simple", False

intent_module = IntentClassificationModule()