from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.core.config import settings

class SQLGenerationModule:
    """
    HLD 3.4: SQL Generation Module
    Generates SQL from user natural language query and context.
    Uses Rule-based Pattern Matching & Predefined Templates when custom models are enabled (zero external LLM dependencies).
    """
    
    async def generate(self, query: str, context: Dict[str, Any]) -> str:
        """
        Generates SQL based on query and context (schema, few-shot, domain, etc.)
        """
        domain = context.get("domain", "general")
        logger.info(f"Generating SQL for domain: {domain} | Query: {query}")
        
        if settings.USE_CUSTOM_MODELS:
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            
            retail_intent = context.get("retail_intent")
            if not retail_intent:
                retail_intent = intent_service.get_retail_intent(query)
                
            entities = context.get("entities", {})
            resolved_entities = entities.get("resolved_entities", {}) if isinstance(entities, dict) else {}
            
            generated_sql = sql_generator.generate(
                query=query,
                retail_intent=retail_intent,
                entities=resolved_entities,
                domain=domain
            )
            return generated_sql

        # Fallback to LLM-based SQL generation if USE_CUSTOM_MODELS is explicitly False
        from app.services.llm import llm_service
        from app.modules.schema_understanding import schema_module
        from app.services.database import db_service
        from app.modules.preprocessing.assets.domain_config import format_few_shots_for_prompt
        from app.modules.learning import learning_service

        schema_str = schema_module.get_schema_string(domain=domain)
        live_schema = db_service.get_schema_info()
        schema_dict = {}
        for item in live_schema:
            t, c = item.split('.')
            if t not in schema_dict:
                schema_dict[t] = []
            schema_dict[t].append(c)
            
        live_schema_str = "ACTUAL DATABASE SCHEMA (ABSOLUTE TRUTH):\n"
        for table, cols in schema_dict.items():
            live_schema_str += f"Table: {table}\nColumns: {', '.join(cols)}\n\n"

        domain_config = learning_service.get_domain_config(domain)
        custom_sql_prompt = domain_config.get("prompts", {}).get("sql")
        domain_prompt = custom_sql_prompt or f"You are an expert SQL assistant for the {domain} domain."
        
        examples = context.get("few_shot_examples", [])
        few_shot_str = format_few_shots_for_prompt(examples) if examples else ""
        
        entities = context.get("entities", {})
        resolved_vals = entities.get("resolved_entities", {}) if isinstance(entities, dict) else {}
        entity_str = ""
        if resolved_vals:
            entity_str = "Resolved Entity Mappings:\n"
            for col, val in resolved_vals.items():
                entity_str += f"- {col}: {val}\n"

        prompt = f"""{domain_prompt}
{live_schema_str}
{entity_str}
{few_shot_str}
User Request: {query}
SQL Query:"""
        try:
            response = await llm_service.generate_response(prompt, model_name=settings.SQL_MODEL)
            cleaned_sql = response.replace("```sql", "").replace("```", "").strip()
            return cleaned_sql
        except Exception as e:
            logger.error(f"LLM SQL Generation Error: {e}")
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            retail_intent = intent_service.get_retail_intent(query)
            return sql_generator.generate(query, retail_intent, domain=domain)

    async def repair(self, query: str, invalid_sql: str, error: str) -> str:
        """
        Repairs invalid SQL.
        """
        if settings.USE_CUSTOM_MODELS:
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            retail_intent = intent_service.get_retail_intent(query)
            logger.info(f"[SQL Repair] Using template fallback for query: '{query}'")
            return sql_generator.generate(query, retail_intent)

        from app.services.llm import llm_service
        prompt = f"""Fix the SQLite query for: "{query}"\nInvalid SQL: {invalid_sql}\nError: {error}\nReturn ONLY corrected SQL."""
        try:
            response = await llm_service.generate_response(prompt)
            return response.replace("```sql", "").replace("```", "").strip()
        except Exception as e:
            logger.error(f"SQL Repair Error: {e}")
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            return sql_generator.generate(query, intent_service.get_retail_intent(query))

sql_generation_module = SQLGenerationModule()
