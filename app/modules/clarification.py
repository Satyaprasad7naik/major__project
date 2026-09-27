from typing import Dict, Any
import json
from app.core.config import settings

class ClarificationModule:
    """
    Generates clarifying questions when user query is ambiguous or incomplete.
    Uses rule-based templates when custom models are enabled (zero external LLM dependencies).
    """
    
    async def generate_clarification(self, query: str, domain: str, conversation_history: list = None) -> str:
        """
        Generates a follow-up question to clarify the user's intent.
        """
        clean_q = query.lower().strip().strip("!").strip(".")
        greetings = {"hi", "hello", "hey", "help", "good morning", "good afternoon", "hi there", "greetings"}
        
        domain_name = domain.replace("_", " ").title()
        if clean_q in greetings:
            return f"Hello! I am InsightOS, your custom AI Data Assistant for the **{domain_name}** domain. Ask me about stockout risk, reorder recommendations, sales trends, or inventory status!"

        if settings.USE_CUSTOM_MODELS:
            return (
                f"I couldn't clearly match your request '{query}' to a database metric. "
                f"Here are a few things you can ask me:\n"
                f"- **Stockout Risk**: 'Which products will run out of stock this week?'\n"
                f"- **Reorder Recommendations**: 'What items need replenishment?'\n"
                f"- **Sales Analysis**: 'Show top performing products and revenue breakdown'\n"
                f"- **Inventory Status**: 'Show current inventory by category'"
            )

        from app.services.llm import llm_service
        from app.modules.learning import learning_service
        
        config = learning_service.get_domain_config(domain)
        schema_context = config.get("schema_context", "")
        
        prompt = f"""
You are a helpful assistant helping clarify database queries in the {domain.upper()} domain.
DATABASE CONTEXT: {schema_context}
Current user query: "{query}"
Task: Suggest 2-3 specific questions they CAN ask about that match the schema.
"""
        try:
            response = await llm_service.generate_response(prompt, model_name=settings.CLARIFICATION_MODEL)
            return response.strip()
        except Exception:
            return "Could you please clarify your request? You can ask about stockout risks, inventory levels, or top sales."

clarification_module = ClarificationModule()
