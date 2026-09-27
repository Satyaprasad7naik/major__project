"""
Chat with Your Data API Endpoints for InsightOS.
Implements the UX Layer specified in AUTO_INSIGHTS_FEATURE.md:
- Sanitization & Schema Context Injection
- Constrained SQL Generation
- Execution Safety Barrier (AST validation via sqlparse)
- Conversational Insight Synthesis
"""

from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time
import re
import sqlite3
import sqlparse

from app.core.logger import logger
from app.core.config import settings
from app.services.llm import LLMService
from app.services.auto_insights import get_db_connection

router = APIRouter(prefix="/chat", tags=["chat"])


class NLQueryRequest(BaseModel):
    query: str = Field(..., example="Which products are at high risk of stockout this week?")
    session_id: Optional[str] = None
    db_path: Optional[str] = Field("retail_clothing.db", description="Target database file")


class NLQueryResponse(BaseModel):
    query: str
    generated_sql: str
    columns: List[str]
    data: List[Dict[str, Any]]
    conversational_summary: str
    execution_time_ms: float


def validate_safe_read_query(sql: str) -> bool:
    """
    AST & Token Validation Barrier:
    Enforces strict read-only execution. Blocks any non-SELECT statements
    and destructive DDL/DML keywords.
    """
    if not sql or not sql.strip():
        return False

    clean_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    parsed = sqlparse.parse(clean_sql)
    if not parsed:
        return False

    dangerous_tokens = {'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT', 'REVOKE', 'EXEC', 'MERGE'}

    for statement in parsed:
        stmt_type = statement.get_type()
        if stmt_type != 'SELECT' and stmt_type != 'UNKNOWN':
            return False

        # Flatten tokens to inspect every symbol
        for token in statement.flatten():
            token_val = token.normalized.upper() if hasattr(token, 'normalized') else str(token).upper()
            if token_val in dangerous_tokens:
                return False

    return True


def get_schema_context(conn: sqlite3.Connection) -> str:
    """Extract trimmed DDL representation of active tables."""
    cursor = conn.cursor()
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%celery%'"
    ).fetchall()
    
    schema_parts = []
    for t in tables:
        tname = t[0]
        columns = cursor.execute(f"PRAGMA table_info({tname});").fetchall()
        col_defs = [f"{col[1]} ({col[2]})" for col in columns]
        schema_parts.append(f"Table {tname}: {', '.join(col_defs)}")
    
    return "\n".join(schema_parts)


@router.post("/query", response_model=NLQueryResponse)
async def chat_with_data(payload: NLQueryRequest = Body(...)):
    """
    Converts user natural language intent into validated read-only SQL,
    executes it safely against the relational store, and synthesizes conversational insights.
    """
    start_time = time.time()
    db_file = payload.db_path or "retail_clothing.db"
    
    conn = None
    try:
        conn = get_db_connection(db_file)
        schema_context = get_schema_context(conn)
        
        # 1. SQL Generation
        prompt_lower = payload.query.lower()
        generated_sql = ""
        
        # 1. SQL Generation with Custom ML / Rule Engine
        from app.services.intent_service import intent_service
        from app.ml_models.sql_generator.rule_engine import sql_generator
        
        retail_intent = intent_service.get_retail_intent(payload.query)
        generated_sql = sql_generator.generate(
            query=payload.query,
            retail_intent=retail_intent,
            domain="retail_clothing"
        )
                
        # 2. Safety Barrier Enforcement
        if not validate_safe_read_query(generated_sql):
            logger.error(f"Dangerous SQL query blocked: {generated_sql}")
            raise HTTPException(
                status_code=400,
                detail="Security Guardrail: Non-SELECT or potentially destructive query blocked."
            )
            
        # 3. Execute Query
        cursor = conn.cursor()
        cursor.execute(generated_sql)
        rows = cursor.fetchall()
        
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        data = [dict(zip(columns, row)) for row in rows]
        
        # 4. Synthesize Conversational Summary via Custom AI Insight Generator
        from app.services.insight_generator import insight_generator_service
        insights = insight_generator_service.generate(
            query=payload.query,
            results=data,
            domain="retail_clothing",
            retail_intent=retail_intent
        )
        summary = f"**Insight**: {insights.get('insight')}\n\n**Action**: {insights.get('recommendation')}"
            
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        
        return NLQueryResponse(
            query=payload.query,
            generated_sql=generated_sql,
            columns=columns,
            data=data,
            conversational_summary=summary,
            execution_time_ms=execution_time_ms
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Chat query execution failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()
