# InsightOS – Full Feature Implementation Guide
**Project:** InsightOS (Virtual Decision Officer)  
**Goal:** Make the system clearly different from normal BI tools by focusing on **Finding → Insight → Recommended Action**

---

## 1. Core Identity (Must Keep)
Every answer must follow this structure:

- **Finding**: What is the current situation
- **Insight**: Why it matters / root cause
- **Recommended Action**: Exact next step the user should take

Never return only raw data or charts.

---

## 2. Features to Implement

### A. Stockout Risk + Reorder Recommendation (High Priority)
- Detect products with low days-of-cover
- Calculate recommended reorder quantity
- Suggest supplier and lead time
- Support questions like:
  - “Which products will run out in the next 7 days?”
  - “How many units of Milk should I reorder?”

### B. Auto-Generated Insights (Proactive)
- Background job (APScheduler) that runs every 1–2 hours
- Automatically detect:
  - High stockout risk
  - Sudden sales drop
  - Critical inventory levels
- Store results in `auto_insights` table
- Show as cards on dashboard (“Today’s Insights”)

### C. Threat-Simulation Testing Mode
- Create a special mode / API to inject fake danger data
- Examples of fake dangers:
  - Extremely low stock
  - Sudden sales crash
  - High pending orders
- System must detect the danger and generate correct alerts
- Log pass/fail results for testing

### D. What-If / Counterfactual Analysis
- Support questions like:
  - “What if sales increase by 30% next week?”
  - “What if supplier is delayed by 4 days?”
- Recalculate stockout risk under the new assumption
- Show before vs after comparison

### E. Confidence Score + Explanation
- Every answer must include:
  - Confidence percentage (e.g. 87%)
  - Short explanation of how the answer was reached
- Add a “Why should I trust this?” expandable section

### F. Action Confirmation (Draft Purchase Order)
- When system recommends reordering:
  - Allow user to click “Create Draft PO”
  - Save a draft purchase order in the database
  - Status = “Draft” (waiting for approval)

### G. Simple Ontology
- Create `ontology.json` or database tables for:
  - Product categories (Dairy, Bakery, etc.)
  - Properties (is_perishable, needs_cold_storage)
  - Relationships
- Use ontology to expand queries (e.g. “perishable items” → Milk, Curd, Cheese)

### H. Safety / Circuit Breakers
- Keep and improve existing safety switches
- Block dangerous SQL
- Force safe responses when risk is critical

---

## 3. Database Changes Required

Create / update these tables:

- `auto_insights`
- `purchase_orders` (for draft POs)
- `ontology_concepts` + `ontology_relations` (optional but recommended)
- Make sure inventory, sales, products, suppliers tables support stockout calculations

---

## 4. Technical Requirements

- Keep using: FastAPI + LangGraph + Gemini + SQLite + React
- Background scheduler: APScheduler
- All new features must work with the existing multi-agent pipeline
- Maintain the self-healing SQL agent
- Dashboard must show:
  - Today’s Insights cards
  - Confidence score
  - Draft PO button when applicable
  - What-If results clearly

---

## 5. Implementation Order (Recommended)

1. Stockout Risk + Reorder logic
2. Auto-Generated Insights + Scheduler
3. Confidence Score + Explanation
4. Draft Purchase Order
5. What-If Analysis
6. Threat Simulation Mode
7. Ontology integration
8. Final UI polish

---

## 6. Success Criteria

- User can ask normal English questions and get Finding + Insight + Action
- System proactively shows important alerts
- User can create a draft purchase order from a recommendation
- What-If questions work
- Threat simulation can be demonstrated live
- Every answer shows confidence + short reasoning

---

## 7. Important Notes for Anti-Gravity

- Prefer simple and working solutions over complex ones
- Reuse existing agents and pipeline as much as possible
- Keep code clean and modular
- Add clear comments
- Update README with the new capabilities
- Make sure the system still runs with `uvicorn`

**Start by implementing Stockout Risk + Auto Insights first.**