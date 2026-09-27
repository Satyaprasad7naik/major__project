# Antigravity Module Specification: Next-Gen Autonomous Enterprise Features

## Overview
This specification outlines the architecture, data contracts, agent graph structures, and implementation steps for integrating four next-generation modules into the enterprise decision intelligence platform. These modules transition the platform from passive analytics to an autonomous, prescriptive operating system.

---

## 1. Autonomous Procurement Agents (The Action Layer)

### Objective
Automate post-stockout-prediction operations by executing multi-agent workflows that inspect supplier agreements, compute economic reorder quantities, and draft structured Purchase Orders (POs) awaiting one-click human confirmation.

### Multi-Agent Architecture (LangGraph State Machine)
The procurement cycle runs as a compiled StateGraph containing specialized agent nodes:

```
                  +-------------------------+
                  |  Trigger: StockoutRisk  |
                  +------------+------------+
                               |
                               v
                  +-------------------------+
                  |  SupplierLookupAgent    |
                  +------------+------------+
                               |
                               v
                  +-------------------------+
                  |  Pricing&VolumeAgent    |
                  +------------+------------+
                               |
                               v
                  +-------------------------+
                  |  DraftGeneratorAgent    |
                  +------------+------------+
                               |
                               v
                  +-------------------------+
                  | Human-in-the-Loop Gate  |
                  +------------+------------+
                        /            \
             (Approved)/              \(Rejected)
                      v                v
          +-------------------+   +--------------------+
          |  DispatchWorker   |   | LogAbortAuditState |
          +-------------------+   +--------------------+
```

### State Schema & Node Contract
```python
from typing import TypedDict, Optional, List
from pydantic import BaseModel, Field

class ProcurementState(TypedDict):
    sku_id: str
    item_name: str
    projected_shortage_units: int
    predicted_stockout_date: str
    supplier_id: Optional[str]
    supplier_email: Optional[str]
    unit_cost: Optional[float]
    recommended_order_quantity: Optional[int]
    total_estimated_cost: Optional[float]
    purchase_order_id: Optional[str]
    draft_email_subject: Optional[str]
    draft_email_body: Optional[str]
    approval_status: str  # 'PENDING_REVIEW', 'APPROVED', 'REJECTED'
    error_log: List[str]
```

### Implementation Checklist
- [ ] **LangGraph Workflow Definition**: Implement `ProcurementStateGraph` with state checkpointing via SQLite/Postgres saver.
- [ ] **Database Lookups**: Create query helpers to fetch preferred vendor records, lead times, and negotiated price tiers.
- [ ] **Action Generation**: Format output into standard purchase requisition records with status `AWAITING_APPROVAL`.
- [ ] **FastAPI Endpoints**:
  - `POST /api/v1/procurement/trigger`: Evaluates low-stock thresholds and starts the agent run.
  - `GET /api/v1/procurement/proposals/pending`: Returns pending PO drafts for dashboard review.
  - `POST /api/v1/procurement/proposals/{po_id}/decision`: Accepts `{"action": "APPROVE" | "REJECT"}`. If approved, dispatches supplier notification via SMTP/API.

---

## 2. "Chat with Your Data" Interface (The UX Layer)

### Objective
Allow non-technical managers and business stakeholders to execute complex analytical queries using natural language. The system converts user intent into validated read-only SQL, executes it against the relational store, and synthesizes conversational insights.

### Pipeline Architecture
1. **Sanitization & Schema Context Injection**: The user prompt is paired with a trimmed DDL representation (tables, columns, foreign keys).
2. **Constrained SQL Generation (Gemini)**: Gemini generates strict SQL dialect queries constrained by business rules.
3. **Execution Safety Barrier**: AST validation blocks any non-`SELECT` statement (`DROP`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`).
4. **Insight Synthesis**: Query tabular results are fed back into Gemini along with the original intent to produce an executive summary and trend explanation.

### Query Contract
```python
class NLQueryRequest(BaseModel):
    query: str = Field(..., example="Which electronics categories are at high risk of stockout next week?")
    session_id: Optional[str] = None

class NLQueryResponse(BaseModel):
    query: str
    generated_sql: str
    columns: List[str]
    data: List[dict]
    conversational_summary: str
    execution_time_ms: float
```

### SQL Guardrail Enforcement Example
```python
import sqlparse

def validate_safe_read_query(sql: str) -> bool:
    parsed = sqlparse.parse(sql)
    for statement in parsed:
        if statement.get_type() != 'SELECT':
            return False
        # Block dangerous keyword tokens
        for token in statement.flatten():
            if token.normalized in {'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT'}:
                return False
    return True
```

### Implementation Checklist
- [ ] **Metadata Catalog Generator**: Build utility to extract active tables (`inventory_items`, `sales_history`, `suppliers`, `stock_levels`).
- [ ] **Prompt Engine**: Define system instructions enforcing dialect adherence, alias conventions, and deterministic output.
- [ ] **FastAPI Streaming Endpoint**: `POST /api/v1/chat/query` supporting server-sent events (SSE) for query generation status and conversational response.
- [ ] **React Frontend Component**: Conversational drawer with integrated syntax-highlighted SQL preview and dynamic table/chart visualization.

---

## 3. Deep Learning Demand Forecasting (The ML Layer)

### Objective
Upgrade baseline reorder calculations to an intelligent time-series forecasting engine utilizing a hybrid Convolutional Neural Network - Long Short-Term Memory (CNN-LSTM) architecture. The model captures both short-term localized fluctuations and long-term seasonal trends across high-SKU inventories.

### Model Architecture
```
  [Input Window: N Days Historical Sales + Exogenous Signals]
                             |
                             v
           [1D Convolutional Layer (Kernel size: 3)]
                   -> Local Pattern Extraction
                             |
                             v
               [MaxPooling1D Layer (Pool: 2)]
                             |
                             v
              [LSTM Layer (64 Hidden Units)]
                   -> Temporal Dependency Capture
                             |
                             v
             [Dense Output Layer (Horizon: H)]
                   -> Multi-step Sales Prediction
```

### Exogenous Features
* **Calendar Signals**: Day of week, month, day of month, weekend indicator.
* **Events & Festivities**: Indicator flags for regional holidays, major shopping festivals, and promotional spikes.
* **Pricing & Discount Deltas**: Historical price elasticity features.

### Dynamic Safety Stock Equation
$$	ext{Safety Stock} = Z 	imes \sqrt{L 	imes \sigma_D^2 + D^2 	imes \sigma_L^2}$$
* Where:
  * $Z$ is the service level factor (e.g., 1.65 for 95%).
  * $L$ is lead time, $\sigma_L$ is lead time standard deviation.
  * $D$ is model-predicted average daily demand over the lead horizon.
  * $\sigma_D^2$ is the variance of forecast errors from the CNN-LSTM model.

### Implementation Checklist
- [ ] **Data Pipeline**: Preprocessing scripts converting tabular transactional logs into rolling sequence matrices $(X \in \mathbb{R}^{B 	imes T 	imes F}, Y \in \mathbb{R}^{B 	imes H})$.
- [ ] **Inference Service**: Python module loading quantized ONNX/TensorFlow/PyTorch model artifacts for low-latency batch inferences.
- [ ] **Scheduled Worker**: Nightly cron job recalculating stockout probabilities and reorder thresholds across active SKUs.
- [ ] **FastAPI Endpoint**: `GET /api/v1/forecast/{sku_id}?horizon=14` returning point predictions, confidence intervals, and recommended safety stock.

---

## 4. Multimodal Invoice Parsing (The Integration Layer)

### Objective
Eliminate manual stock intake and billing ingestion by processing image and PDF invoices using Gemini Multimodal capabilities. The system structures supplier line items, matches them against internal catalog SKUs, and stage-updates stock counts.

### Processing Pipeline
1. **Document Upload**: Multi-page PDF or JPEG/PNG receipt uploaded via frontend file dropzone.
2. **Payload Normalization**: Convert PDF pages to images or process binary streams directly.
3. **Structured Gemini Extraction**: Invoke Gemini with an enforced JSON schema returning invoice metadata and itemized tables.
4. **Entity Resolution**: Fuzzy match raw invoice item descriptions against internal SKU database.
5. **Reconciliation & Ingestion**: Post updates to stock balances or record pending inventory receipts.

### Structured Extraction Schema
```json
{
  "invoice_number": "INV-2026-0891",
  "supplier_name": "Metro Wholesale Logistics",
  "invoice_date": "2026-08-28",
  "currency": "INR",
  "subtotal": 45200.00,
  "tax_amount": 8136.00,
  "total_amount": 53336.00,
  "line_items": [
    {
      "raw_description": "Acoustic Noise-Cancelling Earbuds Pro 12x",
      "quantity": 25,
      "unit_price": 1200.00,
      "total_line_price": 30000.00,
      "matched_sku_id": "SKU-AUDIO-09"
    }
  ]
}
```

### FastAPI Ingestion Handler Skeleton
```python
from fastapi import APIRouter, UploadFile, File, HTTPException
import json

router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])

@router.post("/parse")
async def parse_invoice(file: UploadFile = File(...)):
    contents = await file.read()
    mime_type = file.content_type
    
    if mime_type not in ["application/pdf", "image/png", "image/jpeg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    
    # Process with Gemini Multimodal API using structured output / response_mime_type="application/json"
    # Execute catalog entity resolution
    return {"status": "SUCCESS", "extracted_data": {...}}
```

### Implementation Checklist
- [ ] **FastAPI Multipart Route**: Handle file upload validation and file stream buffer handling.
- [ ] **Gemini Multimodal Invocation**: Configure `gemini-1.5-pro` or `gemini-1.5-flash` with strict response schema enforcing JSON serialization.
- [ ] **Catalog Reconciliation Engine**: Rapid string matching (e.g., token sort ratio / Levenshtein distance) to pair invoice lines with master catalog IDs.
- [ ] **Verification UI**: Interactive screen for warehouse operators to review mapped rows, edit mismatches, and click "Confirm Ingestion".

---

## 5. Implementation Roadmap & Milestones

| Sprint | Focus Area | Deliverables |
|---|---|---|
| **Phase 1** | Multimodal Invoice Ingestion | Upload endpoint, Gemini schema parsing, catalog reconciliation, stock update API |
| **Phase 2** | NL "Chat with Your Data" | Database schema exporter, SQL generation pipeline, safety AST checks, React chat widget |
| **Phase 3** | Deep Learning Demand Engine | Sequence builder, CNN-LSTM training/export, scheduled batch predictor, safety stock math |
| **Phase 4** | Autonomous Procurement Graph | LangGraph state graph, supplier lookup, PO draft generator, human approval UI |