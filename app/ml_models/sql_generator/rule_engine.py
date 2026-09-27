"""
Rule-Based SQL Generator for InsightOS Retail Analytics.
Maps (intent + natural language entities) -> High-precision SQL query
strictly grounded in the live retail database (shop_sales, products, inventory, suppliers, sales_events).
"""

import re
from typing import Dict, Any, Optional, List
from app.core.logger import logger


# ── SQL Templates Grounded in Live Retail Data ───────────────────────────────

SQL_TEMPLATES = {
    # 1. Retail Transactions & Order Log
    "transactions_query": """
        SELECT transaction_id, date, shop_name, city, category, product,
               quantity, unit_price, sales, cost, profit, payment_method, customer_type
        FROM shop_sales
        ORDER BY date DESC
        LIMIT 50
    """,

    # 2. Product Sales Volume & Revenue
    "sales_analysis": """
        SELECT product, category,
               SUM(quantity) AS total_units_sold,
               COUNT(transaction_id) AS num_transactions,
               ROUND(AVG(unit_price), 2) AS avg_unit_price,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_units_sold DESC
        LIMIT 15
    """,

    # 3. Store / Shop Performance
    "sales_analysis_by_shop": """
        SELECT shop_name, city,
               COUNT(transaction_id) AS total_transactions,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY shop_name, city
        ORDER BY total_revenue DESC
    """,

    # 4. Regional / City Performance
    "sales_analysis_by_city": """
        SELECT city,
               COUNT(transaction_id) AS num_transactions,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY city
        ORDER BY total_revenue DESC
    """,

    # 5. Category Performance
    "sales_analysis_by_category": """
        SELECT category,
               COUNT(DISTINCT product) AS num_products,
               SUM(quantity) AS total_units_sold,
               COUNT(transaction_id) AS num_transactions,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY category
        ORDER BY total_revenue DESC
    """,

    # 6. Profit & Margin Analysis
    "profit_analysis": """
        SELECT product, category,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(cost), 2) AS total_cost,
               ROUND(SUM(profit), 2) AS total_profit,
               ROUND((SUM(profit) / MAX(SUM(sales), 1.0)) * 100, 2) AS profit_margin_pct
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_profit DESC
        LIMIT 15
    """,

    # 7. Payment Methods Breakdown
    "payment_methods_query": """
        SELECT payment_method,
               COUNT(transaction_id) AS transaction_count,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY payment_method
        ORDER BY total_sales DESC
    """,

    # 8. Customer Types Breakdown
    "customer_types_query": """
        SELECT customer_type,
               COUNT(transaction_id) AS customer_count,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(profit), 2) AS total_profit,
               ROUND(AVG(sales), 2) AS avg_order_value
        FROM shop_sales
        GROUP BY customer_type
        ORDER BY total_sales DESC
    """,

    # 9. Stockout Risk Analysis (Sales Velocity based on live Excel transactions)
    "stockout_risk": """
        SELECT product, category,
               SUM(quantity) AS total_units_sold,
               COUNT(transaction_id) AS sales_frequency,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(AVG(sales), 2) AS avg_sale_value,
               'High Sales Velocity' AS velocity_status
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_units_sold DESC
        LIMIT 15
    """,

    # 10. Reorder Recommendations
    "reorder_recommendation": """
        SELECT product, category,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(AVG(quantity), 1) AS avg_units_per_order,
               ROUND(SUM(quantity) * 1.5) AS recommended_restock_units
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_units_sold DESC
        LIMIT 15
    """,

    # 11. Inventory Status / Product Performance
    "inventory_status": """
        SELECT product, category,
               COUNT(DISTINCT shop_name) AS shops_selling,
               COUNT(transaction_id) AS total_orders,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_units_sold DESC
        LIMIT 20
    """,

    # 12. Category Breakdown
    "inventory_by_category": """
        SELECT category,
               COUNT(DISTINCT product) AS distinct_products,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY category
        ORDER BY total_units_sold DESC
    """,

    # 13. Stores & Locations
    "general_query_suppliers": """
        SELECT shop_name, city,
               COUNT(DISTINCT product) AS unique_products_sold,
               COUNT(transaction_id) AS total_transactions,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue
        FROM shop_sales
        GROUP BY shop_name, city
        ORDER BY total_revenue DESC
    """,

    # 14. Sync Logs
    "general_query_sync_logs": """
        SELECT id, source_type, file_name, status, rows_synced, synced_at
        FROM sync_logs
        ORDER BY synced_at DESC
        LIMIT 20
    """,

    # 15. Default Product Overview
    "general_query_default": """
        SELECT product, category,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_sales,
               ROUND(SUM(profit), 2) AS total_profit
        FROM shop_sales
        GROUP BY product, category
        ORDER BY total_units_sold DESC
        LIMIT 15
    """,

    # 16. Schema Query
    "schema_query": """
        SELECT name AS table_name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;
    """,

    # 17. Overall Store Summary & Total Revenue / Profit
    "total_summary": """
        SELECT COUNT(transaction_id) AS total_transactions,
               SUM(quantity) AS total_units_sold,
               ROUND(SUM(sales), 2) AS total_revenue,
               ROUND(SUM(cost), 2) AS total_cost,
               ROUND(SUM(profit), 2) AS total_profit,
               ROUND((SUM(profit) / MAX(SUM(sales), 1.0)) * 100, 2) AS overall_profit_margin_pct
        FROM shop_sales
    """,
}


# ── Entity extraction patterns ──────────────────────────────────────────────

_SKU_PATTERN = re.compile(r"SKU[- ]?([A-Za-z0-9_-]+)", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"(?:top|first|last|show|limit)\s*(\d+)", re.IGNORECASE)

_CATEGORY_KEYWORDS = {
    "electronics": "Electronics", "electronic": "Electronics", "audio": "Electronics",
    "gadget": "Electronics", "gadgets": "Electronics", "tech": "Electronics",
    "home": "Home & Kitchen", "kitchen": "Home & Kitchen", "furniture": "Furniture",
    "apparel": "Clothing", "clothing": "Clothing", "fashion": "Clothing",
    "footwear": "Footwear", "shoes": "Footwear", "cosmetics": "Cosmetics",
    "beauty": "Cosmetics", "grocery": "Grocery", "groceries": "Grocery",
    "sports": "Sports", "fitness": "Sports", "books": "Books", "book": "Books"
}

_KNOWN_PRODUCTS = [
    "dumbbells", "resistance band", "study table", "biscuits", "mouse", "chair",
    "earphones", "t-shirt", "jeans", "jacket", "shirt", "sneakers", "boots",
    "sandals", "lipstick", "perfume", "face wash", "moisturizer", "lip balm",
    "cricket bat", "football", "yoga mat", "water bottle", "keyboard", "monitor",
    "charger", "smartwatch", "bed sheet", "curtains", "lamp", "rice", "sugar",
    "oil", "wheat flour", "tea powder", "sofa", "textbook", "skipping rope"
]

_KNOWN_SHOPS = [
    "fitness world", "home needs", "daily needs", "mobile world", "green basket",
    "book corner", "kids zone", "shoe point", "beauty care", "style hub",
    "tech zone", "fresh mart", "gadget hub", "trendy wear", "super save"
]

_KNOWN_CITIES = {
    "mysuru": "Mysuru", "mysore": "Mysuru",
    "udupi": "Udupi",
    "mangalore": "Mangalore", "mangaluru": "Mangalore",
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru"
}

_PAYMENT_KEYWORDS = ["card", "upi", "cash", "net banking", "wallet"]
_CUSTOMER_KEYWORDS = ["new", "returning", "repeat"]


class RuleBasedSQLGenerator:
    """
    Generates SQL queries strictly grounded in the live retail database.
    """

    def generate(
        self,
        query: str,
        retail_intent: str,
        entities: Optional[Dict[str, Any]] = None,
        domain: str = "retail_clothing",
    ) -> str:
        query_lower = query.lower()

        extracted = self._extract_entities(query)
        if entities:
            extracted.update(entities)

        sql = self._select_template(retail_intent, query_lower)
        sql = self._apply_filters(sql, extracted, query_lower)
        sql = " ".join(sql.split())

        logger.info(f"[SQLGenerator] Intent: {retail_intent} -> SQL: {sql[:80]}...")
        return sql

    def _select_template(self, intent: str, query_lower: str) -> str:
        """Select the best SQL template based on intent and query keywords."""

        # 1. Schema Query
        if any(kw in query_lower for kw in ["schema", "database tables", "list tables", "show tables"]):
            return SQL_TEMPLATES["schema_query"]

        # 2. Sync Logs
        if any(kw in query_lower for kw in ["sync log", "sync status", "excel sync"]):
            return SQL_TEMPLATES["general_query_sync_logs"]

        # 3. Overall Total Summary / Revenue / Total Sales / Total Profit
        if any(kw in query_lower for kw in ["total revenue", "overall revenue", "total sales", "overall sales", "total profit", "overall profit", "total cost", "store summary", "business summary"]):
            return SQL_TEMPLATES["total_summary"]

        # 4. Stockout Risk & Critical Inventory
        if intent == "stockout_risk" or any(kw in query_lower for kw in ["stockout", "out of stock", "at risk", "critical stock", "low stock", "urgent attention"]):
            return SQL_TEMPLATES["stockout_risk"]

        # 5. Reorder Recommendations
        if intent == "reorder_recommendation" or any(kw in query_lower for kw in ["reorder", "suggested order", "restock"]):
            return SQL_TEMPLATES["reorder_recommendation"]

        # 6. Profit, Margin & Cost Analysis
        if any(kw in query_lower for kw in ["profit", "margin", "cost", "profitable", "net profit"]):
            return SQL_TEMPLATES["profit_analysis"]

        # 7. Payment Methods Breakdown
        if any(kw in query_lower for kw in ["payment method", "payment mode", "payments", "upi", "card payment", "cash payment"]):
            return SQL_TEMPLATES["payment_methods_query"]

        # 8. Customer Types Breakdown
        if any(kw in query_lower for kw in ["customer type", "new customer", "returning customer", "customer breakdown"]):
            return SQL_TEMPLATES["customer_types_query"]

        # 9. Store / Shop / Branch Analysis
        if any(kw in query_lower for kw in ["shop", "store", "store name", "shop name", "branch", "channel"]):
            return SQL_TEMPLATES["sales_analysis_by_shop"]

        # 10. Regional / City Performance
        if any(kw in query_lower for kw in ["city", "cities", "location", "region"]):
            return SQL_TEMPLATES["sales_analysis_by_city"]

        # 11. Raw Transactions / Orders
        if any(kw in query_lower for kw in ["transaction", "transactions", "orders", "receipts", "order list"]):
            return SQL_TEMPLATES["transactions_query"]

        # 12. Sales & Revenue by Category
        if "category" in query_lower or "categories" in query_lower or "department" in query_lower:
            if any(kw in query_lower for kw in ["inventory", "stock", "level"]):
                return SQL_TEMPLATES["inventory_by_category"]
            return SQL_TEMPLATES["sales_analysis_by_category"]

        # 13. Sales Analysis / Top Selling Products
        if intent == "sales_analysis" or any(kw in query_lower for kw in ["sales", "top selling", "revenue", "sold", "best selling", "volume"]):
            return SQL_TEMPLATES["sales_analysis"]

        # 14. Inventory Status
        if intent == "inventory_status" or any(kw in query_lower for kw in ["inventory", "stock count", "stock level", "in stock"]):
            return SQL_TEMPLATES["inventory_status"]

        # 15. Suppliers & Vendors
        if "supplier" in query_lower or "vendor" in query_lower:
            return SQL_TEMPLATES["general_query_suppliers"]

        # 16. Default
        return SQL_TEMPLATES["sales_analysis"]

    def _extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract structured entities from natural language query."""
        entities = {}
        query_lower = query.lower()

        # Extract SKU
        sku_match = _SKU_PATTERN.search(query)
        if sku_match:
            sku_val = sku_match.group(1).upper()
            entities["sku"] = f"SKU-{sku_val}" if not sku_val.startswith("SKU-") else sku_val

        # Extract Category
        for keyword, category in _CATEGORY_KEYWORDS.items():
            if re.search(rf"\b{re.escape(keyword)}\b", query_lower):
                entities["category"] = category
                break

        # Extract Shop Name
        for shop in _KNOWN_SHOPS:
            if re.search(rf"\b{re.escape(shop)}\b", query_lower):
                entities["shop_name"] = shop.title()
                break

        # Extract City
        for city_kw, city_val in _KNOWN_CITIES.items():
            if re.search(rf"\b{re.escape(city_kw)}\b", query_lower):
                entities["city"] = city_val
                break

        # Extract Product Name
        for p in _KNOWN_PRODUCTS:
            if re.search(rf"\b{re.escape(p)}\b", query_lower):
                entities["product"] = p.title()
                break

        # Extract Payment Method
        for pm in _PAYMENT_KEYWORDS:
            if re.search(rf"\b{re.escape(pm)}\b", query_lower):
                entities["payment_method"] = pm.title()
                break

        # Extract Customer Type
        for ct in _CUSTOMER_KEYWORDS:
            if re.search(rf"\b{re.escape(ct)}\b", query_lower):
                entities["customer_type"] = ct.title()
                break

        # Extract Limit
        limit_match = _LIMIT_PATTERN.search(query)
        if limit_match:
            entities["limit"] = int(limit_match.group(1))

        return entities

    def _apply_filters(self, sql: str, entities: Dict[str, Any], query_lower: str) -> str:
        """Apply entity-based WHERE filters correctly to the SQL template."""
        filters = []
        is_shop_sales = "shop_sales" in sql.lower()

        if "sku" in entities:
            if is_shop_sales:
                prod_name = entities["sku"].replace("SKU-", "").replace("-", " ")
                filters.append(f"UPPER(product) LIKE '%{prod_name.upper()}%'")
            else:
                filters.append(f"p.sku = '{entities['sku']}'")

        if "product" in entities:
            if is_shop_sales:
                filters.append(f"UPPER(product) LIKE '%{entities['product'].upper()}%'")
            else:
                filters.append(f"UPPER(p.style_name) LIKE '%{entities['product'].upper()}%'")

        if "category" in entities:
            if is_shop_sales:
                filters.append(f"UPPER(category) LIKE '%{entities['category'].upper()}%'")
            else:
                filters.append(f"UPPER(p.category) LIKE '%{entities['category'].upper()}%'")

        if "shop_name" in entities and is_shop_sales:
            filters.append(f"UPPER(shop_name) LIKE '%{entities['shop_name'].upper()}%'")

        if "city" in entities and is_shop_sales:
            filters.append(f"UPPER(city) LIKE '%{entities['city'].upper()}%'")

        if "payment_method" in entities and is_shop_sales:
            filters.append(f"UPPER(payment_method) = '{entities['payment_method'].upper()}'")

        if "customer_type" in entities and is_shop_sales:
            filters.append(f"UPPER(customer_type) = '{entities['customer_type'].upper()}'")

        # Apply WHERE filters
        if filters:
            filter_clause = " AND ".join(filters)
            if "WHERE" in sql.upper():
                sql = re.sub(
                    r"(WHERE\s+)",
                    rf"\1{filter_clause} AND ",
                    sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                for kw in ["GROUP BY", "ORDER BY", "LIMIT"]:
                    if kw in sql.upper():
                        idx = sql.upper().index(kw)
                        sql = sql[:idx] + f"WHERE {filter_clause} " + sql[idx:]
                        break
                else:
                    sql = sql.rstrip().rstrip(";") + f" WHERE {filter_clause}"

        # Override LIMIT if specified
        if "limit" in entities:
            limit_val = entities["limit"]
            if "LIMIT" in sql.upper():
                sql = re.sub(r"LIMIT\s+\d+", f"LIMIT {limit_val}", sql, flags=re.IGNORECASE)
            else:
                sql = sql.rstrip().rstrip(";") + f" LIMIT {limit_val}"

        sql = sql.strip()
        if not sql.endswith(";"):
            sql += ";"

        return sql


# Singleton instance
sql_generator = RuleBasedSQLGenerator()
