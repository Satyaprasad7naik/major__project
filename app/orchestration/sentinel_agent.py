from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from app.orchestration.scan_memory import scan_memory
import json

class SentinelBrainstormer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.8
        )

        self.schema_context = """
        ACTUAL TABLES (Retail Clothing Domain):
        - products (sku, style_name, category, size, color, unit_cost, retail_price, supplier_id, created_at)
        - inventory (sku, location, stock_count, reorder_point, last_restocked_at)
        - suppliers (supplier_id, supplier_name, lead_time_days, on_time_rate, country)
        - sales_events (event_id, sku, units_sold, sale_date, channel)
        
        JOIN KEY: products.sku = inventory.sku = sales_events.sku
        SUPPLIER JOIN: products.supplier_id = suppliers.supplier_id
        SKU format: CL-00001 to CL-00120
        """

    async def brainstorm_missions(self, count_per_domain=2):
        # Get adaptive context from scan memory
        adaptive = scan_memory.get_adaptive_context()

        if settings.ADAPTIVE_ENABLED and adaptive["scan_count"] > 0:
            domain_weights = adaptive["domain_weights"]
        else:
            domain_weights = {"retail_clothing": count_per_domain * 4}

        total_count = sum(domain_weights.values())

        prompt = ChatPromptTemplate.from_template("""
            You are the "Sentinel Brain", an autonomous security and compliance agent for a financial platform.
            Your task is to brainstorm dynamic, high-impact "Deep Audit Missions" based on the database schema.

            SCHEMA:
            {schema}

            MISSION ALLOCATION BY DOMAIN:
            - retail_clothing: {retail_count} missions (dead stock, sizing anomalies, supplier delays, reorder point breaches)

            SCAN INTELLIGENCE (from {scan_count} previous scans):

            FOCUS AREAS (generate DEEPER missions on these — they were critical last scan):
            {focus_areas}

            QUERIES TO AVOID (already explored recently — generate NEW angles):
            {avoid_queries}

            GOAL:
            Generate exactly {total_count} distinct audit questions (missions).
            The questions should be sophisticated, seeking hidden patterns or critical risks.
            DIVERSIFY: Do NOT repeat previous queries. Explore new angles each scan.

            RESPONSE FORMAT:
            Provide ONLY a JSON list of objects:
            [
                {{
                    "id": "unique_string",
                    "name": "Short Mission Name",
                    "query": "The natural language question for the AI to solve",
                    "domain": "one of the domains above",
                    "severity": "CRITICAL, HIGH, or MEDIUM"
                }}
            ]
        """)

        chain = prompt | self.llm
        response = await chain.ainvoke({
            "schema": self.schema_context,
            "retail_count": domain_weights.get("retail_clothing", 8),
            "total_count": total_count,
            "scan_count": adaptive["scan_count"],
            "focus_areas": "\n".join(adaptive["focus_areas"]) or "No previous data. This is the first scan.",
            "avoid_queries": "\n".join(f"- {q}" for q in adaptive["avoid_queries"]) or "None — first scan."
        })

        try:
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except Exception as e:
            print(f"Failed to parse brainstormed missions: {e}")
            return []
