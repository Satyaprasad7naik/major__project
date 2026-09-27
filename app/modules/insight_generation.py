import json
from typing import Dict, Any, List
from app.core.logger import logger
from app.core.config import settings

class InsightGenerationModule:
    """
    HLD Section 5: Decision Support & Action Recommendations
    Analyzes query results to provide executive-level insights and actionable recommendations.
    Uses Rule-Based Template Engine when custom models are enabled (zero external LLM dependencies).
    """
    
    async def generate(self, query: str, results: List[Dict[str, Any]], domain: str = "general") -> Dict[str, str]:
        """
        Generates insight and recommendation based on data.
        """
        logger.info(f"Generating insights for {len(results)} rows in domain: {domain}")
        if not results:
            return {
                "insight": "No data found to analyze.",
                "recommendation": "Try broadening your search criteria or checking if the data for this period is available."
            }

        if settings.USE_CUSTOM_MODELS:
            from app.services.insight_generator import insight_generator_service
            from app.services.intent_service import intent_service
            retail_intent = intent_service.get_retail_intent(query)
            return insight_generator_service.generate(
                query=query,
                results=results,
                domain=domain,
                retail_intent=retail_intent
            )

        # Fallback to LLM if explicitly enabled
        from app.services.llm import llm_service
        sample_results = results[:20] 
        results_str = json.dumps(sample_results, indent=2)

        prompt = f"""
You are the Chief Intelligence Officer (CIO) for a major enterprise.
User's Question: "{query}"
Query Results (Sample of {len(sample_results)} rows out of {len(results)}):
{results_str}
Format your response as a JSON object:
{{
  "insight": "Detailed business insight...",
  "recommendation": "Specific actionable steps..."
}}
"""
        try:
            response = await llm_service.generate_response(prompt, model_name=settings.DISCOVERY_MODEL)
            response = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(response)
            return {
                "insight": str(data.get("insight", "Insight generated based on data metrics.")),
                "recommendation": str(data.get("recommendation", "Continue monitoring these trends."))
            }
        except Exception as e:
            logger.error(f"Insight Generation Error: {e}")
            from app.services.insight_generator import insight_generator_service
            return insight_generator_service.generate(query, results, domain)

insight_module = InsightGenerationModule()
