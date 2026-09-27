# Mixo: Autonomous Retail Decision Engine & Custom AI Intelligence

[![Demo Verification](https://img.shields.io/badge/Demo-Verified_100%25-brightgreen.svg)]()
[![Custom AI](https://img.shields.io/badge/AI_Engine-Custom_Trained_Models-blue.svg)]()
[![Offline Mode](https://img.shields.io/badge/External_LLM-Not_Required_100%25_Offline-success.svg)]()

> **InsightOS** operates with **custom trained AI models** specifically designed for retail inventory, demand forecasting, stockout risk scoring, and rule-based decision support. **No external LLMs or third-party API keys are required.**

---

## 🧠 Custom Trained AI Models Architecture

InsightOS replaces external LLM dependencies with a dedicated, lightweight, and explainable ML architecture:

```text
                     User Natural Language Query
                                 ↓
            [1] Custom Intent Classifier (TF-IDF + LogReg)
                                 ↓
                     [2] Orchestration Router
                                 ↓
         ┌───────────────────────┼────────────────────────┐
         ↓                       ↓                        ↓
[Demand Forecaster]     [Stockout Risk Model]   [Reorder Calculator]
 (RandomForest/XGBoost)   (Hybrid Rule + ML)       (Policy Engine)
         └───────────────────────┬────────────────────────┘
                                 ↓
             [3] Deterministic SQL Rule Generator
                                 ↓
             [4] Executive Insight Synthesis Engine
                                 ↓
               Finding → Insight → Recommended Action
```

### 1. **Intent Classification Model** (`app/ml_models/intent_classifier`)
- **Architecture**: TF-IDF N-gram Vectorizer (1-2 ngrams) + Multiclass Logistic Regression with class-balancing.
- **Classes**: `stockout_risk`, `reorder_recommendation`, `sales_analysis`, `inventory_status`, `general_query`, `schema_query`, `off_topic`.
- **Latency**: `< 1ms` inference time.

### 2. **Demand Forecasting Model** (`app/ml_models/demand_forecasting`)
- **Architecture**: Ensemble Regressor (Random Forest / XGBoost) trained on historical multi-channel sales events.
- **Features**: Day of week, month, weekend indicators, rolling 7d/14d/30d sales velocity, price and stock ratios.
- **Output**: 7-day SKU demand forecast with 95% confidence intervals and dynamic safety stock requirements.

### 3. **Stockout Risk Engine** (`app/ml_models/stockout_risk`)
- **Architecture**: Hybrid ML + inventory state estimator.
- **Metrics**: Days of Cover ($DoC = \frac{\text{Stock}}{\text{Daily Demand}}$), Lead-Time Buffer Ratio, and Stockout Probability.
- **Risk Tiers**: `Critical` (≤ 2 days), `High` (≤ 5 days), `Medium` (≤ 10 days), `Low` (> 10 days).

### 4. **Reorder Quantity Calculator** (`app/ml_models/reorder_quantity`)
- **Formula**:
  $$\text{Reorder Qty} = \begin{cases} \max(\text{Reorder Point} \times 3, 15) & \text{if } \text{Stock} \le 0 \\ (\text{Reorder Point} - \text{Stock}) + \text{Reorder Point} & \text{if } \text{Stock} < \text{Reorder Point} \\ 0 & \text{otherwise} \end{cases}$$
- Adjusted for supplier lead time coverage and safety buffers.

---

## 📁 Project Structure

```text
InsightOS/
├── app/
│   ├── main.py                  # FastAPI Application Entrypoint
│   ├── api/                      # REST API Endpoints & Routes
│   ├── services/                 # Business logic, sync pipelines (Google Sheets, Tally, Excel)
│   ├── core/                     # Configuration, Database engines, Logging, Resilient LLM
│   ├── modules/                  # NL2SQL, Schema, Entity Extraction, & Reporting Modules
│   └── ml_models/                # Custom ML models (Intent, Demand, Stockout, Reorder)
├── frontend/                     # Interactive Web Dashboard UI
├── live_data/                    # Incoming Excel sheets & Google Sheets mirrored backups
├── models/                       # Serialized offline ML model artifacts
├── scripts/                      # Utility, migration, benchmark, & CLI tools
├── tests/                        # Automated Pytest Suite
├── .env                          # Local Environment Configuration
├── requirements.txt              # Production Dependencies
└── README.md                     # Platform Documentation
```

---

## ✨ Key Capabilities

*   **⚡ 100% Offline & Zero API Cost**: Runs completely locally with zero external API dependencies.
*   **📊 Finding → Insight → Recommended Action**: Executive-level synthesis for category managers.
*   **🔄 Automated Data Sync**: Live sync pipelines for Tally ERP, Excel spreadsheets, and CSV feeds.
*   **🛒 Autonomous Procurement**: Generates and manages Purchase Orders (DRAFT → APPROVED → SENT).
*   **🌿 Scope 1-3 Carbon Accounting**: Calculates logistics, transit, and packaging ESG metrics per SKU.

---

## 🚀 Getting Started

### 1. Environment Setup
```bash
python -m venv venv
./venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file with your Google Gemini API Key:
```env
GOOGLE_API_KEY=your_gemini_key
DB_PATH=./derivinsightnew.db
```

### 3. Run the Platform
```bash
python -m uvicorn app.main:app --reload --port 8080
```

---

## 💎 Demo Verification (Try These)

| Domain | Executive Question | Impact |
| :--- | :--- | :--- |
| **Risk** | *"Show me all users and their risk levels."* | **Critical Profile Alert** |
| **Security**| *"Show me failed logins by reason and IP address."* | **Threat Intelligence** |
| **Growth** | *"Which countries have the highest active users?"* | **Market Optimization** |
| **Fraud** | *"List all transactions in 'FLAGGED' status."* | **AML Monitoring** |

## 🔄 Automated Multi-Source Live Data Synchronization

InsightOS provides **zero-touch automated data ingestion** across multiple enterprise sources into the Retail & Financial Ontologies:

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Tally ERP/Prime │       │  Google Sheets  │       │ Network Folder  │
│ (Hourly/Folder) │       │ (Every 15-30 m) │       │  (Every 5-10 m) │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         └────────────────┼────────┴─────────────────────────┘
                          │
                          ▼
            ┌───────────────────────────┐
            │ InsightOS Sync Services   │
            │ (Tally / Sheets / Network)│
            └─────────────┬─────────────┘
                          │
                          ▼
            ┌───────────────────────────┐
            │ InsightOS SQLite Database │
            │ (retail_clothing.db)      │
            └─────────────┬─────────────┘
                          │
                          ▼
            ┌───────────────────────────┐
            │ Auto-Generated Insights   │
            │ & Executive Alert Engine  │
            └───────────────────────────┘
```

### 1. Tally ERP 9 / TallyPrime Auto Sync (Every 1 Hour)
* **How It Works**: Connects to Tally's native HTTP XML Server (Port 9000) or monitors an auto-export directory (`TALLY_EXPORT_FOLDER`).
* **Enabling Port 9000 in TallyPrime**: `F1 (Help)` $\rightarrow$ `Settings` $\rightarrow$ `Connectivity` $\rightarrow$ Set `Client/Server` to `Both`, `Enable ODBC` to `Yes`, `Port` to `9000`.
* **Configuration (`.env`)**:
  ```env
  TALLY_SYNC_ENABLED=true
  TALLY_HOST=localhost
  TALLY_PORT=9000
  TALLY_SYNC_INTERVAL_MINUTES=60
  # TALLY_EXPORT_FOLDER=D:/tally_exports
  ```

### 2. Google Sheets Live Sync (Every 15–30 Min)
* **How It Works**: Ingests `Products`, `Inventory`, and `Sales` worksheets via Google Sheets API (Service Account) or direct HTTP CSV Export.
* **Configuration (`.env`)**:
  ```env
  GOOGLE_SHEETS_ENABLED=true
  GOOGLE_SHEET_ID=your_google_sheet_id_here
  GOOGLE_CREDENTIALS_FILE=credentials.json
  GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES=30
  ```

### 3. Shared Network Folder Sync (Every 5–10 Min)
* **How It Works**: Automatically watches a shared network folder (e.g. `\\server\shared\live_data` or mapped drive `Z:\data`), detects new or updated `.xlsx`/`.xls` files, and ingests them with lock/offline tolerance.
* **Configuration (`.env`)**:
  ```env
  NETWORK_FOLDER_ENABLED=true
  NETWORK_FOLDER_PATH=\\server\shared\live_data
  NETWORK_FOLDER_SYNC_INTERVAL_MINUTES=5
  ```

### 4. Sync REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/sync/now` | Trigger local `live_data/` Excel sync |
| `POST` | `/api/v1/sync/tally/auto` | Trigger automated Tally pull (folder or HTTP Port 9000) |
| `POST` | `/api/v1/sync/google-sheets` | Trigger Google Sheets live sync |
| `POST` | `/api/v1/sync/network-folder`| Trigger shared network folder sync |
| `GET` | `/api/v1/sync/status/all` | Unified multi-source sync status & logs |
| `GET` | `/api/v1/sync/tally/ping` | Ping Tally ERP XML server on Port 9000 |

---

Developed for the **Deriv Hackathon** – *Empowering Executives with Data-First Decisioning.*
