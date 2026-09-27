# Context: Auto-generated Insights (Proactive Insights)

## Project
InsightOS – AI-powered Decision Support System

## Feature Name
Auto-generated Insights (Proactive Insights)

## What this feature does
The system automatically scans the database every few hours and generates important alerts **without the user asking**.

Example output:
- “3 products need urgent attention today”
- “Milk 1L is at high risk of stockout”
- “Sudden sales drop detected in Bread”

---

## Requirements

### 1. Background Job
- Use **APScheduler**
- Run the insight generation job every **2 hours**
- Also run the job once when the server starts

### 2. What the job should check
The background job must detect these situations:

1. **Stockout Risk**
   - Products where Days of Cover < 3
   - Days of Cover = Current Stock / Average Daily Sales

2. **Sudden Sales Drop**
   - Products whose recent sales dropped significantly compared to previous period

3. **High Risk Items**
   - Products that are both low in stock and have high demand

### 3. Database Table
Create this table if it does not exist:

```sql
CREATE TABLE IF NOT EXISTS auto_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_type TEXT,              -- 'stockout', 'sales_drop', 'high_risk'
    title TEXT,
    description TEXT,
    severity TEXT,                  -- 'high', 'medium', 'low'
    product_id INTEGER,
    product_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT 0
);