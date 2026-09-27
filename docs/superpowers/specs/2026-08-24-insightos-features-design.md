# InsightOS Feature Implementation Design Document

**Date:** 2026-08-24  
**Project:** InsightOS (Virtual Decision Officer)  
**Status:** Draft for Review

---

## 1. Executive Summary

This document describes the architectural design for implementing the InsightOS feature set on top of the existing NL2SQL pipeline (DerivInsight). The goal is to transform the system from a reactive query tool into a proactive **Virtual Decision Officer** that delivers **Finding → Insight → Recommended Action** for every interaction.

### Scope
- 8 major features across 3 phases
- Domain-agnostic design supporting retail_clothing, banking_finance, insurance
- Reuse existing LangGraph pipeline, FastAPI, SQLite, React stack
- New database tables, background scheduler, API endpoints, UI components

---

## 2. Current Architecture Analysis

### Existing Pipeline (LangGraph)
```
User Query → Intent Classification → SQL Generation → Validation → Execution → Visualization → Insights
```

**Key Extension Points:**
- Post-execution, pre-insight: Inject stockout analysis
- Intent classification: Add WHAT_IF, SIMULATION intent types
- Response formatting: Add confidence, explanation, draft PO actions
- Background: APScheduler for proactive insights

### Domain Configuration
Each domain (`retail_clothing`, `banking_finance`, `insurance`) has:
- `domain_config.json` with schema context, prompts, few-shots
- Independent SQLite database (retail_clothing.db, derivinsightnew.db, etc.)

---

## 3. Feature Design Specifications

### 3.1 Stockout Risk + Reorder Logic (Priority 1)

#### Module: `app/modules/stockout_analyzer.py`

**Purpose:** Calculate days-of-cover and reorder recommendations for any domain with inventory/sales data.

**Input:** Domain, optional SKU filter, optional days-ahead threshold  
**Output:** List of at-risk products with Finding, Insight, Recommended Action, Confidence

**Calculation Methods (Configurable per Domain):**
```python
# Method 1: Simple threshold (uses existing reorder_point column)
at_risk = stock_count <= reorder_point

# Method 2: Days-of-cover (requires sales_events/history)
avg_daily_sales = sum(units_sold last 30 days) / 30
days_of_cover = stock_count / max(avg_daily_sales, 0.1)
at_risk = days_of_cover <= threshold_days
```

**Reorder Quantity Formula:**
```
reorder_qty = max(
    reorder_point * 2 - stock_count,           # Restock to 2x reorder point
    lead_time_days * avg_daily_sales * 1.5     # Cover lead time + 50% buffer
)
```

**Supplier Selection:** Join products → suppliers, pick highest on_time_rate

**API Endpoint:** `GET /api/v1/stockout/risk?domain={domain}&days=7&method=auto`

**Integration:** New node in LangGraph after `execute_query`, before `insight_recommendation`

---

### 3.2 Auto-Generated Insights + Scheduler (Priority 2)

#### Module: `app/services/auto_insights_scheduler.py`

**Purpose:** Background job running every 1-2 hours to proactively detect anomalies.

**Scheduler Configuration:**
```python
# Config via environment
SCHEDULER_MODE = "embedded" | "standalone"  # Default: embedded
SCHEDULER_INTERVAL_MINUTES = 90             # Default: 90 min
```

**Detection Rules (Domain-Configurable):**
| Rule | Trigger | Severity |
|------|---------|----------|
| Stockout Risk | days_of_cover <= 7 | HIGH |
| Critical Stockout | stock_count == 0 | CRITICAL |
| Sales Drop | current_7d_avg < 0.5 * prior_7d_avg | MEDIUM |
| Supplier Delay Risk | lead_time_days > 14 AND on_time_rate < 0.8 | MEDIUM |

**Storage:** New `auto_insights` table
```sql
CREATE TABLE auto_insights (
    insight_id TEXT PRIMARY KEY,           -- INS-YYYYMMDD-XXXX
    domain TEXT NOT NULL,
    insight_type TEXT NOT NULL,            -- 'stockout_risk', 'sales_drop', 'critical_inventory', 'supplier_risk'
    severity TEXT NOT NULL,                -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    title TEXT NOT NULL,
    description TEXT,
    payload_json TEXT,                     -- Full context for drill-down
    sku TEXT,                              -- Optional reference
    supplier_id TEXT,                      -- Optional reference
    status TEXT DEFAULT 'ACTIVE',          -- 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT
);
```

**API Endpoints:**
- `GET /api/v1/insights/today?domain={domain}` - Today's insights for dashboard
- `POST /api/v1/insights/{id}/acknowledge` - Mark as acknowledged
- `GET /api/v1/insights/history?domain={domain}&days=7` - Historical insights

**Dashboard Integration:** "Today's Insights" cards showing title, severity, one-line description, "View Details" action

---

### 3.3 Confidence Score + Explanation (Priority 3)

#### Extensions to: `app/models/state.py`, `app/modules/insight_generation.py`, `frontend/script.js`

**Response Model Extension:**
```python
class QueryResponse(BaseModel):
    # ... existing fields ...
    confidence: Optional[float] = None          # 0.0 - 1.0
    explanation: Optional[str] = None           # Short explanation
    trust_section: Optional[Dict[str, Any]] = None  # "Why should I trust this?" data
```

**Confidence Calculation:**
```
confidence = (
    intent_confidence * 0.3 +
    sql_validity_confidence * 0.2 +
    result_quality_confidence * 0.3 +
    domain_expertise_boost * 0.2
)

# Where:
# - intent_confidence: from intent_module.classify()
# - sql_validity_confidence: 1.0 if valid on first try, 0.7 if repaired, 0.3 if failed
# - result_quality_confidence: min(1.0, row_count / 10) * data_completeness
# - domain_expertise_boost: 0.1 if domain-specific few-shots matched
```

**Explanation Template:**
```
"This answer was generated by:
1. Classifying your question as [intent] with [X]% confidence
2. Generating SQL using [domain]-specific schema and examples
3. Executing against [N] rows of live data
4. Analyzing results with domain-aware insight engine
Confidence: [Y]% - [Reason for confidence level]"
```

**UI:** Expandable "Why should I trust this?" section in results panel showing the explanation and confidence breakdown.

---

### 3.4 Draft Purchase Order (Priority 4)

#### Module: `app/modules/purchase_order.py`

**Purpose:** Convert reorder recommendations into actionable draft POs.

**New Table:**
```sql
CREATE TABLE purchase_orders (
    po_id TEXT PRIMARY KEY,                -- PO-YYYYMMDD-XXXX
    sku TEXT NOT NULL REFERENCES products(sku),
    qty INTEGER NOT NULL,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    unit_cost REAL,
    total_cost REAL,
    status TEXT DEFAULT 'DRAFT',           -- 'DRAFT', 'APPROVED', 'SENT', 'RECEIVED', 'CANCELLED'
    recommended_by TEXT,                   -- 'auto_insight' | 'manual' | 'what_if'
    insight_id TEXT REFERENCES auto_insights(insight_id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT
);
```

**API Endpoints:**
- `POST /api/v1/purchase-orders/draft` - Create from recommendation
  ```json
  {
    "sku": "CL-00001",
    "qty": 50,
    "supplier_id": "SUP-006",
    "source": "stockout_recommendation",
    "insight_id": "INS-20260824-0001"
  }
  ```
- `GET /api/v1/purchase-orders?status=DRAFT` - List draft POs
- `POST /api/v1/purchase-orders/{po_id}/approve` - Approve draft
- `POST /api/v1/purchase-orders/{po_id}/cancel` - Cancel draft

**UI:** "Create Draft PO" button appears in recommendation section when stockout risk detected. Clicking opens modal with pre-filled details, user confirms → POST to API → shows success + PO ID.

---

### 3.5 What-If / Counterfactual Analysis (Priority 5)

#### Module: `app/modules/what_if_engine.py`

**Purpose:** Allow users to simulate scenarios and see projected impact.

**New Intent Type:** `WHAT_IF` (added to intent classification)

**Supported Scenarios:**
| Scenario | Parameter | Example Query |
|----------|-----------|---------------|
| Sales increase | `sales_multiplier: 1.3` | "What if sales increase 30% next week?" |
| Supplier delay | `supplier_delay_days: 4` | "What if supplier SUP-002 is delayed 4 days?" |
| Demand shift | `category: "Shirts", shift: 0.5` | "What if Shirts demand drops 50%?" |
| New product | `sku: "NEW-001", initial_stock: 100` | "What if we launch NEW-001 with 100 units?" |

**Processing Flow:**
1. Parse natural language → extract scenario parameters
2. Clone current inventory/sales state
3. Apply scenario modifications
4. Re-run stockout analysis on modified state
5. Return before/after comparison

**Output Format:**
```json
{
  "scenario": "Sales increase 30%",
  "before": { "at_risk_skus": 5, "critical_skus": 1 },
  "after": { "at_risk_skus": 12, "critical_skus": 4 },
  "delta": { "at_risk_skus": +7, "critical_skus": +3 },
  "recommendations": ["Pre-order 200 units for SKU CL-00003", ...],
  "confidence": 0.82
}
```

**API Endpoint:** `POST /api/v1/what-if`
```json
{
  "query": "What if sales increase by 30% next week?",
  "domain": "retail_clothing",
  "parameters": { "sales_multiplier": 1.3 }
}
```

---

### 3.6 Threat Simulation Mode (Priority 6)

#### Module: `app/modules/threat_simulation.py`

**Purpose:** Testing/validation mode to inject synthetic danger scenarios and verify detection.

**API Endpoint:** `POST /api/v1/simulation/inject`
```json
{
  "scenario": "critical_stockout",
  "domain": "retail_clothing",
  "parameters": {
    "target_skus": ["CL-00001", "CL-00002"],
    "stock_override": 0
  }
}
```

**Built-in Scenarios:**
| Scenario | Injection | Expected Detection |
|----------|-----------|-------------------|
| Critical Stockout | Set stock_count = 0 for N SKUs | CRITICAL stockout alert |
| Sales Crash | Zero out last 7 days sales_events | Sales drop alert |
| Supplier Failure | Set on_time_rate = 0.1 | Supplier risk alert |
| Demand Surge | Multiply recent sales by 5 | Stockout risk alert |

**Validation Flow:**
1. Backup current state (or use transaction rollback)
2. Apply injection
3. Run full detection pipeline (stockout + auto-insights)
4. Verify expected alerts generated
5. Restore state
6. Log pass/fail to `simulation_results` table

**Results Table:**
```sql
CREATE TABLE simulation_results (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    domain TEXT NOT NULL,
    parameters TEXT,           -- JSON
    expected_alerts TEXT,      -- JSON array
    actual_alerts TEXT,        -- JSON array
    passed BOOLEAN,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 3.7 Simple Ontology (Priority 7)

#### File: `app/data/ontology/ontology.json`

**Purpose:** Enable query expansion (e.g., "perishable items" → all dairy products)

**Structure:**
```json
{
  "version": "1.0",
  "domains": {
    "retail_clothing": {
      "categories": {
        "Shirts": { "parent": "Apparel", "properties": {} },
        "T-Shirts": { "parent": "Apparel", "properties": {} },
        "Denim": { "parent": "Apparel", "properties": {} },
        "Outerwear": { "parent": "Apparel", "properties": {"seasonal": true} },
        "Dresses": { "parent": "Apparel", "properties": {} },
        "Trousers": { "parent": "Apparel", "properties": {} }
      },
      "properties": {
        "is_perishable": false,
        "needs_cold_storage": false,
        "seasonal": { "type": "boolean", "description": "Seasonal demand patterns" }
      },
      "synonyms": {
        "tops": ["Shirts", "T-Shirts"],
        "bottoms": ["Denim", "Trousers"],
        "warm clothes": ["Outerwear"],
        "summer wear": ["Dresses", "T-Shirts"]
      }
    },
    "grocery": {
      "categories": {
        "Dairy": { "parent": "Perishables", "properties": {"is_perishable": true, "needs_cold_storage": true} },
        "Bakery": { "parent": "Perishables", "properties": {"is_perishable": true, "needs_cold_storage": false} },
        "Produce": { "parent": "Perishables", "properties": {"is_perishable": true, "needs_cold_storage": true} }
      },
      "properties": {
        "is_perishable": { "type": "boolean" },
        "needs_cold_storage": { "type": "boolean" }
      },
      "synonyms": {
        "perishable items": ["Dairy", "Bakery", "Produce"],
        "cold storage items": ["Dairy", "Produce"]
      }
    }
  }
}
```

**Integration Point:** `app/modules/preprocessing/components/entity_extractor.py`
- When extracting entities, check ontology for synonym expansion
- "perishable items" → expands to category filter for Dairy, Bakery, Produce
- Used in SQL generation via resolved entities

---

### 3.8 Safety / Circuit Breakers (Ongoing)

#### Enhancements to: `app/modules/validation.py`, `app/modules/sql_generation.py`

**SQL Injection Prevention:**
- Block: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `TRUNCATE` without explicit allowlist
- Block: `--`, `;`, `/*`, `*/`, `UNION`, `EXEC`, `xp_` in generated SQL
- Allow only: `SELECT`, `WITH` (CTE)

**Circuit Breakers:**
```python
# In validation_module.validate(sql)
DANGEROUS_PATTERNS = [
    r'\bDROP\s+TABLE\b',
    r'\bDELETE\s+FROM\b(?!\s+WHERE)',  # DELETE without WHERE
    r'\bUPDATE\s+\w+\s+SET\b(?!\s+WHERE)',  # UPDATE without WHERE
    r'\bTRUNCATE\s+TABLE\b',
    r';\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)',
]

CRITICAL_RISK_RESPONSE = {
    "status": "blocked",
    "message": "Query blocked: Critical risk operation detected",
    "finding": "Attempted dangerous SQL operation",
    "insight": "System prevented potential data loss",
    "recommended_action": "Rephrase query as read-only SELECT statement"
}
```

---

## 4. Database Migration Plan

### New Tables (Run via migration script)

```sql
-- 1. auto_insights
CREATE TABLE auto_insights (
    insight_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    payload_json TEXT,
    sku TEXT,
    supplier_id TEXT,
    status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT
);
CREATE INDEX idx_auto_insights_domain_status ON auto_insights(domain, status);
CREATE INDEX idx_auto_insights_created ON auto_insights(created_at DESC);

-- 2. purchase_orders
CREATE TABLE purchase_orders (
    po_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL,
    supplier_id TEXT NOT NULL,
    unit_cost REAL,
    total_cost REAL,
    status TEXT DEFAULT 'DRAFT',
    recommended_by TEXT,
    insight_id TEXT REFERENCES auto_insights(insight_id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT
);
CREATE INDEX idx_po_status ON purchase_orders(status);
CREATE INDEX idx_po_sku ON purchase_orders(sku);

-- 3. simulation_results
CREATE TABLE simulation_results (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    domain TEXT NOT NULL,
    parameters TEXT,
    expected_alerts TEXT,
    actual_alerts TEXT,
    passed BOOLEAN,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Existing Tables (Verify Support)
- `inventory`: Has `stock_count`, `reorder_point`, `last_restocked_at` ✓
- `sales_events`: Has `sku`, `units_sold`, `sale_date`, `channel` ✓
- `products`: Has `sku`, `supplier_id`, `category` ✓
- `suppliers`: Has `supplier_id`, `lead_time_days`, `on_time_rate` ✓

---

## 5. API Endpoint Summary

| Feature | Method | Endpoint | Description |
|---------|--------|----------|-------------|
| Stockout Risk | GET | `/api/v1/stockout/risk` | Get at-risk products |
| Stockout Detail | GET | `/api/v1/stockout/sku/{sku}` | Detail for single SKU |
| Today's Insights | GET | `/api/v1/insights/today` | Dashboard cards |
| Insight History | GET | `/api/v1/insights/history` | Paginated history |
| Acknowledge Insight | POST | `/api/v1/insights/{id}/acknowledge` | Mark acknowledged |
| Draft PO Create | POST | `/api/v1/purchase-orders/draft` | Create draft PO |
| Draft PO List | GET | `/api/v1/purchase-orders` | List with filters |
| Draft PO Approve | POST | `/api/v1/purchase-orders/{id}/approve` | Approve draft |
| What-If Analysis | POST | `/api/v1/what-if` | Counterfactual simulation |
| Threat Inject | POST | `/api/v1/simulation/inject` | Inject test scenario |
| Simulation Results | GET | `/api/v1/simulation/results` | Test history |

---

## 6. Frontend Changes

### New Components (React/Vanilla JS)

1. **InsightsDashboard** - "Today's Insights" cards grid
2. **StockoutRiskPanel** - Table of at-risk SKUs with days-of-cover
3. **ConfidenceBadge** - Shows confidence % with expandable trust section
4. **DraftPOModal** - Create/approve purchase orders
5. **WhatIfPanel** - Scenario input + before/after comparison
6. **SimulationPanel** - Threat simulation controls (dev mode)

### Integration Points
- Add "Insights" tab to main navigation
- Extend results panel with confidence + trust section
- Add "Create Draft PO" button to recommendation display
- Add "What-If" button to query input area

---

## 7. Configuration

### New Environment Variables
```bash
# Scheduler
SCHEDULER_MODE=embedded              # embedded | standalone
SCHEDULER_INTERVAL_MINUTES=90        # Auto-insights frequency

# Stockout
DEFAULT_STOCKOUT_METHOD=auto         # simple | days_of_cover | auto
DEFAULT_STOCKOUT_THRESHOLD_DAYS=7    # Days ahead to flag

# Confidence
CONFIDENCE_MIN_THRESHOLD=0.5         # Below this, show low confidence warning

# Safety
SQL_SAFETY_STRICT=true               # Enable strict validation

# Ontology
ONTOLOGY_PATH=app/data/ontology/ontology.json
```

---

## 8. Testing Strategy

### Unit Tests
- Stockout calculations (both methods)
- Reorder quantity formulas
- Confidence scoring components
- Ontology expansion logic
- What-if state cloning and modification

### Integration Tests
- Full pipeline: query → stockout analysis → insight → recommendation
- Auto-insights scheduler: runs, detects, stores, exposes via API
- Draft PO: create → list → approve → status change
- What-if: scenario → modified state → comparison output
- Threat simulation: inject → detect → verify → cleanup

### E2E Tests (Playwright)
- User asks "Which products at risk?" → sees Finding/Insight/Action
- Auto-insights appear on dashboard after scheduler runs
- Click "Create Draft PO" → modal → confirm → PO appears in list
- What-if question → shows before/after comparison

---

## 9. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Database migrations (auto_insights, purchase_orders, simulation_results)
- [ ] StockoutRiskAnalyzer module with both calculation methods
- [ ] LangGraph integration node
- [ ] API endpoints for stockout risk
- [ ] Basic frontend stockout panel

### Phase 2: Proactive Intelligence (Week 2)
- [ ] AutoInsightsScheduler with APScheduler
- [ ] Detection rules for all 4 insight types
- [ ] Today's Insights API + dashboard cards
- [ ] Confidence scoring in response model
- [ ] Trust section UI

### Phase 3: Action & Simulation (Week 3)
- [ ] Draft PO module + API + UI
- [ ] What-if engine + intent classification
- [ ] What-if API + comparison UI
- [ ] Threat simulation module + API
- [ ] Ontology.json + entity extractor integration

### Phase 4: Polish & Hardening (Week 4)
- [ ] Safety/circuit breaker enhancements
- [ ] Cross-domain testing (retail, banking, insurance)
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] README updates

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Scheduler blocks main thread | Medium | High | Run in separate thread; use `run_in_background` config |
| Domain-agnostic logic too complex | Medium | Medium | Start with retail_clothing, add domain configs incrementally |
| What-if state mutation bugs | Medium | High | Deep clone state; use immutable patterns; thorough tests |
| Ontology doesn't match actual data | Low | Medium | Validate ontology against live schema on startup |
| Breaking existing pipeline | Low | High | Feature flags; comprehensive regression tests |

---

## 11. Success Criteria (from context.md)

- [ ] User asks natural language → gets Finding + Insight + Action
- [ ] System proactively shows alerts on dashboard
- [ ] User creates draft PO from recommendation
- [ ] What-if questions work with before/after comparison
- [ ] Threat simulation demonstrable live
- [ ] Every answer shows confidence + reasoning

---

## 12. Appendix: File Structure Changes

```
app/
├── modules/
│   ├── stockout_analyzer.py          # NEW
│   ├── purchase_order.py             # NEW
│   ├── what_if_engine.py             # NEW
│   ├── threat_simulation.py          # NEW
│   ├── insight_generation.py         # MODIFY (add confidence)
│   ├── validation.py                 # MODIFY (safety enhancements)
│   └── preprocessing/components/
│       └── entity_extractor.py       # MODIFY (ontology integration)
├── services/
│   ├── auto_insights_scheduler.py    # NEW
│   └── database.py                   # MODIFY (new table init)
├── orchestration/
│   └── workflow.py                   # MODIFY (new nodes)
├── api/
│   ├── endpoints.py                  # MODIFY (new routes)
│   └── stockout_endpoints.py         # NEW
├── models/
│   └── state.py                      # MODIFY (new response fields)
└── data/ontology/
    └── ontology.json                 # NEW

frontend/
├── index.html                        # MODIFY (new tabs/sections)
├── script.js                         # MODIFY (new components)
└── styles.css                        # MODIFY (new styles)

docs/superpowers/specs/
└── 2026-08-24-insightos-features-design.md  # THIS FILE
```

---

*End of Design Document*