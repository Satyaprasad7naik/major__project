# Domain-specific prompts and few-shot examples for Retail Clothing Domain

from typing import Dict, List, Any

# ============================================================
# DOMAIN-SPECIFIC SYSTEM PROMPTS
# ============================================================

DOMAIN_PROMPTS: Dict[str, str] = {
    "retail_clothing": """
You are a Retail Operations Analyst for the platform.
Your focus is on inventory velocity, dead stock, sizing distribution, and supplier reliability.

Key areas of concern:
- Dead stock (aged inventory with no recent sell-through)
- Sizing anomalies within a style
- Supplier lead-time and on-time delivery performance
- Reorder point breaches

Use tables: products, inventory, suppliers, sales_events
Prioritize: stock_count, sale_date recency, lead_time_days, on_time_rate
""",
    "general": """
You are a Retail Operations Analyst for the platform.
Your focus is on inventory velocity, dead stock, sizing distribution, and supplier reliability.

Key areas of concern:
- Dead stock (aged inventory with no recent sell-through)
- Sizing anomalies within a style
- Supplier lead-time and on-time delivery performance
- Reorder point breaches

Use tables: products, inventory, suppliers, sales_events
Prioritize: stock_count, sale_date recency, lead_time_days, on_time_rate
"""
}

# ============================================================
# DOMAIN-SPECIFIC FEW-SHOT EXAMPLES
# ============================================================

DOMAIN_FEW_SHOTS: Dict[str, List[Dict[str, str]]] = {
    "retail_clothing": [
        {
            "question": "Show me dead stock older than 90 days",
            "sql": "SELECT p.sku, p.style_name, p.size, i.stock_count FROM products p JOIN inventory i ON p.sku = i.sku WHERE i.stock_count > 0 AND p.sku NOT IN (SELECT sku FROM sales_events WHERE sale_date >= date('now', '-90 days'));"
        },
        {
            "question": "Which suppliers are consistently delayed",
            "sql": "SELECT supplier_name, lead_time_days, on_time_rate FROM suppliers WHERE on_time_rate < 0.85 ORDER BY on_time_rate ASC;"
        },
        {
            "question": "Find sizing anomalies for the Oxford Shirt style",
            "sql": "SELECT p.size, i.stock_count FROM products p JOIN inventory i ON p.sku = i.sku WHERE UPPER(p.style_name) = 'OXFORD SHIRT';"
        }
    ],
    "general": [
        {
            "question": "Show me dead stock older than 90 days",
            "sql": "SELECT p.sku, p.style_name, p.size, i.stock_count FROM products p JOIN inventory i ON p.sku = i.sku WHERE i.stock_count > 0 AND p.sku NOT IN (SELECT sku FROM sales_events WHERE sale_date >= date('now', '-90 days'));"
        },
        {
            "question": "Which suppliers are consistently delayed",
            "sql": "SELECT supplier_name, lead_time_days, on_time_rate FROM suppliers WHERE on_time_rate < 0.85 ORDER BY on_time_rate ASC;"
        },
        {
            "question": "Find sizing anomalies for the Oxford Shirt style",
            "sql": "SELECT p.size, i.stock_count FROM products p JOIN inventory i ON p.sku = i.sku WHERE UPPER(p.style_name) = 'OXFORD SHIRT';"
        }
    ]
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_domain_prompt(domain: str) -> str:
    """Get the system prompt for a specific domain."""
    return DOMAIN_PROMPTS.get(domain, DOMAIN_PROMPTS["general"])

def get_domain_few_shots(domain: str) -> List[Dict[str, str]]:
    """Get the few-shot examples for a specific domain."""
    return DOMAIN_FEW_SHOTS.get(domain, DOMAIN_FEW_SHOTS["general"])

def format_few_shots_for_prompt(examples: List[Dict[str, str]]) -> str:
    """Format few-shot examples into a string for the prompt."""
    formatted = []
    for i, ex in enumerate(examples, 1):
        formatted.append(f"Example {i}:")
        formatted.append(f"Question: {ex['question']}")
        formatted.append(f"SQL: {ex['sql']}")
        formatted.append("")
    return "\\n".join(formatted)
