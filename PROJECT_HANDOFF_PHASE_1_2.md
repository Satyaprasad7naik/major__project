# DerivInsight: Enterprise Architectural Handoff & State Matrix

**System:** DerivInsight (Internal branding: **InsightOS**)
**Document Type:** Engineering Source of Truth
**Audience:** Senior engineers onboarding to backend, orchestration, or infrastructure work
**Scope of this document:** Phase 1 — Executive Summary & System Health, Phase 2 — Infrastructure & Component Matrix

---

## Phase 1: Executive Summary & System Health

### 1.1 What This System Is

DerivInsight is a dual-mode AI intelligence platform: it answers direct natural-language questions about business data (**Reactive Mode**), and it independently generates and investigates its own audit hypotheses without a human prompting it (**Proactive Mode**). These are not two products bolted together — they share the same database layer, the same LLM provider abstraction, and the same risk-scoring primitives, but they are triggered differently and run on different code paths.

**Reactive Mode — NL2SQL Pipeline**

A user submits a question in plain English. The request passes through a fixed, ordered pipeline:

1. **Intent Classification** — the model classifies the query as `SELECT`, `SCHEMA_QUERY`, `OFF_TOPIC`, or similar, and flags ambiguous requests for clarification rather than guessing.
2. **SQL Generation** — a domain-scoped prompt (see Phase 4 in the companion document) produces a candidate SQL statement, grounded in the active domain's schema context.
3. **Validation** — `sqlglot` parses the candidate for structural correctness and rejects any statement containing `DROP`, regardless of syntactic validity.
4. **Execution** — the validated statement runs against `derivinsightnew.db` via SQLAlchemy.
5. **Insight Synthesis** — results are passed back through the LLM layer to produce an executive-readable narrative, not just a raw result set.

**Proactive Mode — Sentinel Autonomous Audit**

`SentinelBrainstormer` runs independently of any user query. On each cycle it:

1. Reads the current adaptive domain weights from `SessionScopedScanMemory.get_adaptive_context()`.
2. Generates a set of "missions" — self-directed audit questions — distributed across the five domains (`security`, `compliance`, `risk`, `operations`, `retail_clothing`) in proportion to those weights.
3. Executes each mission through the same NL2SQL execution path used by Reactive Mode.
4. Scores, correlates, and records results back into scan memory, which in turn reshapes the weights used on the *next* cycle — the system's proactive behavior is self-reinforcing, not static.

### 1.2 Process Topology

The system runs as **two independently deployed processes**, each with a distinct failure domain:

| Process | Role | Entry Point | Failure Blast Radius |
|---|---|---|---|
| **API Gateway** | Serves all REST endpoints, mounts the frontend, executes the synchronous NL2SQL pipeline, invokes AI agents on demand | `python -m uvicorn app.main:app --reload --port 8080` | User-facing outage — no query or dashboard access — but the alert worker keeps running unaffected. |
| **Background Alert Worker** | Runs a continuous polling loop (default **5.0s** tick interval, overridable via `ENGINE_TICK_INTERVAL`), drains queued events from `derivinsight_alerts.db`, evaluates alert conditions, updates worker health state | `python -m app.workers.engine_worker` | Autonomous alerting silently stops — the API stays fully responsive, so this failure mode is easy to miss without actively checking worker status. |

Both processes read from the same codebase but do **not** share an in-memory state — all cross-process coordination happens through the filesystem (`scan_memory_sessions/`) or the database (`worker_status`, `alert_history`). This is a deliberate architecture: it means either process can be restarted independently without corrupting the other's state, at the cost of coordination being eventually-consistent rather than instant.

**Deployment target.** `app/core/config.py` declares a full set of `ECS_*` settings (`ECS_CLUSTER = "HackathonDerivBackend"`, `ECS_LAUNCH_TYPE = "FARGATE"`, separate task-definition and container-name settings for the engine worker and the event generator worker). This confirms the intended production deployment model is **two independently-scheduled AWS ECS Fargate tasks**, mirroring the two-process local model exactly — local dual-terminal execution is not a shortcut, it is a faithful simulation of the production topology.

### 1.3 Current System Health

| Signal | State | Basis |
|---|---|---|
| API Gateway boot | **Healthy** | Clean `DatabaseService` and `LLMService` initialization confirmed in application logs on every observed start. |
| Global exception handling | **Present and active** | `app/main.py` registers a catch-all `@app.exception_handler(Exception)` that logs the full traceback and returns a structured `500` with a `detail` field — no unhandled exception in the API process produces an opaque, traceback-free response to the client. |
| CORS policy | **Open — `allow_origins=["*"]`** | Explicitly configured in `app/main.py`, commented `# In production, replace with specific origins`. This is a known, self-documented placeholder — track it as a pre-production hardening item, not an oversight. |
| Background worker startup | **At risk** | The worker's import chain (`engine_worker` → `alert_engine` → orchestration modules → `sentinel_agent` → `scan_memory`) has a documented open dependency gap; see the companion Incident Ledger (Phase 5) for the exact defect and fix. |
| Redis dependency | **Optional, but must be present in the environment if configured** | The circuit breaker (Phase 3) tolerates Redis being *unreachable*; it does not tolerate the `redis` Python package being *absent* from the environment — that failure occurs before the circuit breaker's own `try/except` can engage, at import time. |

### 1.4 Reading This Document

Sections in this document are written as **current, verified state**, not as a narrative of what changed from a previous draft. Where a component has a known limitation or an open fix, it is stated plainly in-line and again in the Incident Ledger — treat any such note as an action item, not background color.

---

## Phase 2: Infrastructure & Component Matrix

### 2.1 Full Technology Stack

| Layer | Technology | Version Floor (`requirements.txt`) | Notes |
|---|---|---|---|
| Runtime | Python | 3.13 (Conda or venv managed) | — |
| API Framework | FastAPI | `>=0.100.0` | — |
| ASGI Server | Uvicorn | `>=0.23.0` | Runs with `--reload` in local dev |
| Orchestration | LangGraph | `>=0.0.10` | Graph-based pipeline scaffolding |
| Orchestration | LangChain | `>=0.1.0`, `langchain-core>=0.3.0` | Core agent/chain abstractions |
| ORM | SQLAlchemy | `>=2.0.0` | Used for both SQLite databases |
| SQL Safety | sqlglot | `>=18.0.0` | Parse/validate layer ahead of execution |
| Embeddings | sentence-transformers | `>=2.2.2` | Present; `faiss-cpu` is explicitly commented out in `requirements.txt`, indicating vector-index retrieval is not currently wired in, despite the embedding library being installed |
| Cache / Coordination | Redis | `>=5.0.0` | Optional at runtime, required as an installed package if `REDIS_URL`/`REDIS_HOST` is set |
| Cloud SDK | boto3 | `>=1.28.0` | Backing the ECS worker-task management described in §1.2 |
| Observability | opentelemetry-api | `>=1.20.0` | Present as a dependency; instrumentation wiring should be confirmed separately, not assumed from the dependency alone |
| LLM — Google | google-generativeai, langchain-google-genai | `>=0.3.0`, `>=2.0.0` | Backs the Gemini fallback provider |
| LLM — OpenAI-compatible | openai, langchain-openai | `>=2.0.0`, `>=0.1.0` | Backs both the OpenAI provider and the Qubrid provider (Qubrid is consumed via an OpenAI-compatible client) |
| LLM — Anthropic | langchain-anthropic | `>=0.1.0` | **Declared as a dependency but not referenced anywhere in `app/` at present** — no `ChatAnthropic` import or Anthropic-keyed provider branch exists in `llm.py`. Treat as available-but-unwired, not as an active provider. |
| Fuzzy Matching | fuzzywuzzy, python-Levenshtein | `>=0.18.0`, `>=0.23.0` | Used in schema/column retrieval matching |
| HTTP Client | httpx | `>=0.25.0` | — |
| DB Driver — MySQL | PyMySQL | `>=1.0` | Declared; not the active driver in any environment observed (see Phase 3, Database Fallback) |
| Config | pydantic, pydantic-settings, python-dotenv | `>=2.0.0`, `>=2.0.0`, `>=1.0.0` | Backs the `Settings` class in `app/core/config.py` |
| Frontend | Vanilla JS + Chart.js | — | `frontend/index.html`, `script.js`, `styles.css` — no build step, served directly as static files |

### 2.2 Port & Static Routing Topology

The API Gateway binds to **port 8080** exclusively, confirmed at the exact source of truth — the bottom of `app/main.py`:

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Full router registration**, in the order FastAPI actually mounts them:

```python
app.include_router(api_router, prefix=settings.API_V1_STR)          # /api/v1/query, /api/v1/alert
app.include_router(alerts_router)                                    # alert engine control + read endpoints
app.include_router(dashboard_router)                                 # dashboard CRUD
app.include_router(db_test_router)                                   # raw table/schema introspection
app.include_router(sentinel_router, prefix="/api/v1/sentinel", tags=["sentinel"])
app.include_router(redis_test_router)                                # /ping, /read-write, /info
```

| Route | Purpose | Router File |
|---|---|---|
| `/` | Serves `frontend/index.html` directly (not via the `/static` mount) | `app/main.py` |
| `/static/*` | Mounts the entire `frontend/` directory as static assets | `app/main.py` |
| `/styles.css`, `/script.js` | Explicit top-level convenience routes, in addition to `/static/` | `app/main.py` |
| `/health` | Liveness check, returns `{"status": "healthy"}` unconditionally — **not** a dependency-aware readiness check; it does not verify DB or LLM connectivity | `app/main.py` |
| `/api/v1/query`, `/api/v1/alert` | Primary NL2SQL endpoint and manual alert trigger | `app/api/endpoints.py` |
| `/api/v1/sentinel/*` | Autonomous scan trigger, scan history, streaming scan | `app/api/sentinel.py` |
| `/docs` | Auto-generated OpenAPI/Swagger UI (FastAPI default, always on unless explicitly disabled) | FastAPI internal |

**Middleware.** A single `CORSMiddleware` is registered with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]` — maximally permissive, explicitly flagged in-code as a placeholder for a production origin allowlist. A global exception handler is also registered ahead of any router-level error handling, guaranteeing every unhandled exception across all six routers returns a consistent `{"message": "Internal Server Error", "detail": str(exc)}` JSON body rather than a bare ASGI 500.

### 2.3 Dual SQLite Database Isolation

The system intentionally maintains **two separate SQLite databases**, each with its own schema file and its own connection lifecycle — this is a deliberate isolation boundary, confirmed by inspecting both schema definitions directly, not an inferred convention.

#### `derivinsightnew.db` — Primary Business Data

Resolved via `DATABASE_URL` (defaults to `sqlite:///./derivinsightnew.db` if unset), schema sourced from `app/files/derivinsight_schema.sql`. Confirmed tables:

| Table | Purpose |
|---|---|
| `users` | Registered accounts — `user_id` (format `USR-XXXX`), email, full name, ISO-3166 country code, KYC/risk fields |
| `transactions` | Financial transaction records tied to `users` |
| `login_events` | Authentication event history, the primary signal source for anomaly/fraud detection |
| `alert_rules` | User-facing rule definitions for the primary business schema (distinct from `metric_specs` in the alerts database — see below) |
| `alerts` | Alert instances tied to `alert_rules` |
| `audit_logs` | System audit trail |
| `dashboards` | Saved dashboard configurations |
| `query_history` | Historical record of executed NL2SQL queries |

#### `derivinsight_alerts.db` — Alert Engine State

Hardcoded via `ALERTS_DB_PATH = "derivinsight_alerts.db"` in `app/services/alert_engine.py` — **not** controlled by `DATABASE_URL`, and not overridable via environment variable in the current code. Schema sourced from `app/files/alerts_schema.sql` (authored as MySQL DDL — `AUTO_INCREMENT`, `TINYINT(1)` — but executed against SQLite locally, which accepts this syntax permissively; treat the schema file's MySQL dialect as evidence of production intent to run this specific database on MySQL/RDS eventually, distinct from the primary database's fallback behavior). Confirmed tables:

| Table | Purpose |
|---|---|
| `events` | Raw ingested events from all sources (`login`, `transaction`, `kyc`, etc.), with a `processed` flag |
| `metric_specs` | Alert rule configuration — name, source table, filter JSON, sliding-window duration (`window_sec`), `threshold`, `severity`, `is_active` |
| `alert_history` | Every trigger/resolution action against a `metric_spec`, foreign-keyed to `metric_specs.metric_id` |
| `anomaly_history` | One row per metric, rolled up from `alert_history` — current alert count and severity per metric |
| `metric_windows` | Sliding-window bookkeeping supporting the threshold evaluation logic |
| `dashboards` | A **separate** `dashboards` table exists in this schema too — namespaced entirely apart from the primary database's `dashboards` table; the two are not the same table and do not share rows |

**Why this separation matters operationally:** the Alert Worker writes to `derivinsight_alerts.db` continuously, on every tick, independent of whether any user is actively querying the API. Under SQLite's file-level locking model, co-locating this write-heavy workload with the primary business database would risk lock contention against read-heavy NL2SQL queries. The schema split removes that contention entirely, at the cost of any cross-database query needing to be composed at the application layer rather than via a single SQL join.

### 2.4 Adjacent Infrastructure Declared in Configuration

Beyond the database and cache layers already covered, `app/core/config.py` declares two further integration surfaces worth onboarding engineers knowing about even though they sit outside the core request path:

- **Slack alerting** — `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` (default `sentinnelanomalies`), `SLACK_ALERT_MIN_SEVERITY` (default `HIGH`). Both `slack_notifier.py` and this configuration block confirm Sentinel-detected anomalies at or above `HIGH` severity are intended to push directly to a Slack channel, independent of the dashboard UI.
- **Feature flags** — `DEEP_DIVE_ENABLED` (default `True`, `DEEP_DIVE_MAX_DEPTH = 2`), `CORRELATION_ENABLED` (default `True`), `ADAPTIVE_ENABLED` (default `True`). These gate, respectively: whether Sentinel missions can recursively investigate their own findings up to two levels deep, whether cross-mission correlation runs, and whether the adaptive domain-weighting formula (Phase 4) is applied at all versus a flat/uniform weighting. All three default to **on** — disabling any of them is a deliberate degrade, not the baseline state.
