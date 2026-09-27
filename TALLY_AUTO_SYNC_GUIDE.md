# Automated Tally to InsightOS Synchronization Guide

## 1. Overview & Architecture

InsightOS provides **zero-touch, fully automated data synchronization** from **Tally ERP 9 / TallyPrime** into InsightOS. 

### The Automated Flow:
```text
┌─────────────────────────────────┐
│     Tally ERP 9 / TallyPrime    │
│  (HTTP / XML Server on Port 9000)│
└────────────────┬────────────────┘
                 │
                 │ 1. Scheduled XML Pull / Query
                 ▼
┌─────────────────────────────────┐
│ InsightOS Tally Sync Service    │
│ (app/services/tally_sync.py)    │
└────────────────┬────────────────┘
                 │
                 │ 2. Transforms into normalized Excel files
                 ▼
┌─────────────────────────────────┐
│       live_data/ Directory      │
│  - inventory.xlsx               │
│  - sales.xlsx                   │
│  - products.xlsx                │
└────────────────┬────────────────┘
                 │
                 │ 3. Automated Excel Sync & DB Upsert
                 ▼
┌─────────────────────────────────┐
│    InsightOS SQLite Ontology    │
│   (retail_clothing.db)          │
└────────────────┬────────────────┘
                 │
                 │ 4. Proactive Anomaly Detection
                 ▼
┌─────────────────────────────────┐
│ Auto Insights & Alert Dispatch  │
│  - Stockout Risks Detected      │
│  - 1-Click PO Generation        │
│  - Email & Slack Notifications  │
└─────────────────────────────────┘
```

---

## 2. Enabling Tally XML/ODBC Server (1-Time Setup in Tally)

To allow InsightOS to pull data automatically, ensure Tally is configured to accept XML/ODBC requests:

### In TallyPrime:
1. Open **TallyPrime**.
2. Press **F1 (Help)** $\rightarrow$ **Settings** $\rightarrow$ **Connectivity**.
3. Set **Client/Server configuration** to:
   - **TallyPrime acts as**: `Both` (or `Server`)
   - **Enable ODBC**: `Yes`
   - **Port**: `9000` (default)
4. Restart TallyPrime to apply the settings.

### In Tally.ERP 9:
1. Open **Tally.ERP 9**.
2. Press **F12 (Configure)** $\rightarrow$ **Advanced Configurations**.
3. Under **Client/Server Configuration**:
   - **Tally.ERP 9 acts as**: `Both`
   - **Enable ODBC Server**: `Yes`
   - **Port**: `9000`
4. Press `Enter` and restart Tally.ERP 9.

---

## 3. How Synchronization Operates

### Mode 1: Fully Automated Internal Scheduler (Zero Setup Needed)
When the InsightOS FastAPI backend runs (`python -m uvicorn app.main:app --port 8080`), APScheduler automatically:
1. Pings Tally on `http://localhost:9000` every 10 minutes.
2. If Tally is running, extracts live stock balances and sales records.
3. Automatically updates `live_data/inventory.xlsx` and `live_data/sales.xlsx`.
4. Ingests changes into the database and refreshes **Auto Insights** and alerts.

### Mode 2: Dedicated Background Daemon (For Dedicated Tally Machines)
If Tally runs on a separate office desktop or dedicated server:
Double-click **`run_tally_sync.bat`** or run:
```bash
python scripts/tally_auto_exporter.py --host localhost --port 9000 --interval 300
```
This runs continuously every 5 minutes, auto-refreshing `live_data/` and pushing updates to InsightOS.

### Mode 3: On-Demand REST API Endpoints
You can trigger or monitor the Tally synchronization via HTTP REST API:

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/sync/tally/ping` | `GET` | Tests connection to Tally XML server (returns online status and latency). |
| `/api/v1/sync/tally/auto-pull` | `POST` | Triggers immediate automated data extraction from Tally into `live_data/` and database. |
| `/api/v1/sync/tally/export-excel`| `POST` | Converts a provided Tally XML payload into Excel sheets in `live_data/`. |
| `/api/v1/sync/tally/xml` | `POST` | Direct XML ingestion into SQLite tables. |
| `/api/v1/sync/status` | `GET` | Retrieves full sync logs and last execution timestamps. |

---

## 4. Testing & Verification

1. **Verify Tally Server Ping**:
   ```bash
   curl http://localhost:8080/api/v1/sync/tally/ping
   ```
   *Expected Response:*
   ```json
   {
     "online": true,
     "url": "http://localhost:9000",
     "latency_ms": 12.4,
     "message": "Tally XML server is online and responding."
   }
   ```

2. **Trigger On-Demand Auto-Pull**:
   ```bash
   curl -X POST http://localhost:8080/api/v1/sync/tally/auto-pull
   ```

3. **Check Updated Excel Spreadsheets**:
   Inspect `live_data/inventory.xlsx` and `live_data/sales.xlsx` to confirm updated product quantities and transactions.
