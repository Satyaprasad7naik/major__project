from typing import List, Dict, Any, Optional
from app.services.llm import llm_service
import json

class VisualizationModule:
    """
    Analyzes query results and recommends the best visualization type.
    """
    
    async def recommend(self, query: str, sql: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Determines the best chart type and configuration using deterministic local heuristics in 0ms.
        """
        if not results:
            return None
            
        columns = list(results[0].keys())
        return self._heuristic_fallback(columns, results)
            
    def _heuristic_fallback(self, columns: List[str], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simple heuristic if LLM fails"""
        # Detect numeric columns
        numeric_cols = [c for c in columns if isinstance(results[0][c], (int, float))]
        date_cols = [c for c in columns if "date" in c.lower() or "time" in c.lower() or "at" in c.lower()]
        label_cols = [c for c in columns if c not in numeric_cols]
        
        if not numeric_cols:
            return {"chart_type": "table", "title": "Data Results"}
            
        x_key = date_cols[0] if date_cols else (label_cols[0] if label_cols else columns[0])
        y_key = numeric_cols[0]
        
        chart_type = "line" if date_cols else "bar"
        
        return {
            "chart_type": chart_type,
            "title": f"{y_key} by {x_key}",
            "x_axis_key": x_key,
            "y_axis_key": y_key,
            "label": y_key,
            "description": "Auto-generated fallback chart"
        }

visualization_module = VisualizationModule()
