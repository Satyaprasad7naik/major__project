## Phase 5: Incident Ledger & System Hardening

Every entry below reflects direct inspection of the current codebase — not the intake brief's claims taken at face value. Status values are: **Resolved** (verified fixed in code), **Stable** (verified working as intended, no defect found), or **Open** (verified defect, with an exact fix).

### 5.1 Resolved Items

| Item | Verified Fix Location | Detail |
|---|---|---|
| Domain configuration syntax | `app/modules/preprocessing/assets/domain_config.py` | Parses cleanly under `ast.parse()` — all five domain prompt blocks (`security`, `compliance`, `risk`, `operations`, `retail_clothing`) load without a `SyntaxError`. No malformed dictionary literals present. |
| Redis `NoneType` guards | `app/services/worker_registry.py`, `_init_redis()` | Explicit `if not self.redis_url:` check precedes any attempted connection or string operation on the URL. No `.startswith()`, `.split()`, or similar string method is called against a value that could be `None` at that point in the control flow. |
| Redis infrastructure-hostname leak | `app/core/config.py` | `REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST", None)` — defaults to `None`, annotated in-code with `# SECURITY FIX: Defaults to None to prevent infrastructure leak via source code`. No live AWS ElastiCache/Valkey hostname ships as a Python-level default anywhere in `config.py`. |
| Package alignment (`requirements.txt`) | `requirements.txt` | `google-generativeai>=0.3.0`, `langchain-openai>=0.1.0`, and `sqlglot>=18.0.0` are all present with explicit version floors, alongside the full supporting set (`langgraph`, `langchain-google-genai`, `pymysql`, `redis`, `boto3`). Declared dependencies are internally consistent with what the code actually imports, with one exception noted in 5.2. |

### 5.2 Stable, No Action Required

| Item | Verified Detail |
|---|---|
| Worker exception boundary (Engine Worker only) | `app/workers/engine_worker.py` wraps `engine.run_engine(tick_interval=tick_interval)` in a `try/except Exception`, logs the fatal trace with `exc_info=True`, and calls `engine.mark_worker_failed(reason=str(exc))` before exiting with a non-zero status code. The catch-log-persist-exit sequence is complete and correctly ordered. |
| `sqlglot` DROP denylist | `app/modules/validation.py` rejects any candidate SQL statement containing the substring `DROP` (case-insensitive) independent of `sqlglot`'s own parse result — a defense-in-depth check that does not rely solely on the parser correctly identifying a `DROP` statement's AST node type. |

### 5.3 Open Items — Action Required

#### 5.3.1 `worker_status` table does not exist — `mark_worker_failed()` silently no-ops

**Severity: High.** This is a newly confirmed defect, not previously documented.

`AlertEngineService.mark_worker_failed()` in `app/services/alert_engine.py` executes:

```python
def mark_worker_failed(self, reason: str) -> None:
    """Persist an explicit FAILED status the dashboard can surface, instead of a silent process exit."""
    try:
        self.execute(
            "UPDATE worker_status SET status = 'FAILED', last_error = :reason, "
            "failed_at = datetime('now') WHERE worker_name = 'engine'",
            {"reason": reason}
        )
        print(f"[AlertEngineService] Worker marked FAILED: {reason}")
    except Exception as e:
        print(f"Could not mark worker failed in DB: {e}")
```

A repository-wide search confirms **no `CREATE TABLE worker_status` statement exists anywhere** — not in `app/files/alerts_schema.sql`, not in `app/files/derivinsight_schema.sql`, not in any Python migration or `init_dashboard_db.py`-style bootstrap script. The `UPDATE` statement above will raise `sqlite3.OperationalError: no such table: worker_status` on every invocation.

Because this call is itself wrapped in a `try/except Exception as e: print(...)`, the failure does not propagate — it is swallowed and printed to stdout. **The net effect is that the entire "FAILED status persistence" mechanism described elsewhere in this document as the worker's crash-visibility path is currently non-functional.** A crashed engine worker exits cleanly and logs its own fatal trace, but the dashboard-visible `worker_status` row this was designed to produce is never written, because the table backing it was never created.

**Fix — add to `app/files/alerts_schema.sql`:**

```sql
CREATE TABLE IF NOT EXISTS worker_status (
    worker_name VARCHAR(50) PRIMARY KEY,   -- 'engine' | 'generator'
    status      VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    last_error  TEXT,
    started_at  TIMESTAMP,
    failed_at   TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO worker_status (worker_name, status) VALUES ('engine', 'UNKNOWN');
INSERT OR IGNORE INTO worker_status (worker_name, status) VALUES ('generator', 'UNKNOWN');
```

This must be applied to `derivinsight_alerts.db` (via `DatabaseService._execute_sql_file` / the existing schema-initialization path) before `mark_worker_failed()` can succeed. Until this table exists, treat the worker's true failure state as **observable only via process exit code and stdout logs**, not via the database or dashboard.

#### 5.3.2 `scan_memory` singleton import — still open

`app/orchestration/sentinel_agent.py` imports:

```python
from app.orchestration.scan_memory import scan_memory
```

No module-level assignment `scan_memory = SessionScopedScanMemory()` exists in `scan_memory.py`. This raises `ImportError: cannot import name 'scan_memory' from 'app.orchestration.scan_memory'` at import time, which blocks any code path that imports `sentinel_agent` — including Sentinel-mode worker startup and any API route that lazily imports `SentinelBrainstormer`.

**Fix — append to the end of `app/orchestration/scan_memory.py`:**

```python
# Module-level singleton — imported by name in sentinel_agent.py and any
# other module that needs a shared, process-local default session.
# Per-request/tenant code should still construct SessionScopedScanMemory(session_id=...)
# explicitly; this singleton exists only to satisfy the existing import contract.
scan_memory = SessionScopedScanMemory()
```

#### 5.3.3 Asymmetric worker hardening — `generator_worker.py` has no failure boundary

**Severity: Medium.** Not previously documented.

`app/workers/engine_worker.py` wraps its main loop in `try/except` with logging and `mark_worker_failed()`. `app/workers/generator_worker.py` does **not** follow the same pattern — `generator.start_all(...)` is called directly, with no surrounding `try/except`:

```python
print("[GeneratorWorker] Starting event generator")
generator.start_all(
    user_interval=user_interval,
    login_interval=(login_min, login_max),
    txn_interval=(txn_min, txn_max),
    kyc_interval=(kyc_min, kyc_max),
)
try:
    while not _shutdown.is_set():
        _shutdown.wait(timeout=1)
finally:
    generator.stop_all()
```

The only `try/finally` present guarantees `generator.stop_all()` runs on shutdown — it does not catch or log a fatal exception raised by `start_all()` itself, and there is no equivalent `mark_worker_failed()` call for the `'generator'` worker name. A crash in `start_all()` will propagate as a bare, unlogged traceback to stderr, with no structured record anywhere.

**Fix — mirror the Engine Worker's pattern in `generator_worker.py`:**

```python
print("[GeneratorWorker] Starting event generator")
try:
    generator.start_all(
        user_interval=user_interval,
        login_interval=(login_min, login_max),
        txn_interval=(txn_min, txn_max),
        kyc_interval=(kyc_min, kyc_max),
    )
    while not _shutdown.is_set():
        _shutdown.wait(timeout=1)
except Exception as exc:
    logger.error(f"[GeneratorWorker] Fatal error: {exc}", exc_info=True)
    try:
        engine_service_ref.mark_worker_failed(reason=str(exc))  # worker_name='generator' variant
    except Exception as mark_exc:
        logger.error(f"[GeneratorWorker] Could not persist FAILED state: {mark_exc}")
    sys.exit(1)
finally:
    generator.stop_all()
```

This depends on 5.3.1 being fixed first — there is no point persisting a `'generator'` failure row into a table that does not yet exist.

#### 5.3.4 `.env.example` ships a live, uncommented database credential

**Severity: High — hygiene, not a code defect.**

Unlike the project's working `.env` file (where the equivalent line is commented out), `.env.example` — the file explicitly intended to be copied by every new engineer — contains an **active, uncommented** `DATABASE_URL` pointing at a specific AWS RDS MySQL instance, with an inline plaintext username and password. Any engineer who runs `cp .env.example .env` without editing this line will have their local environment attempt to connect directly to that production-looking RDS endpoint using a real-looking credential embedded in version control history.

**Fix — `.env.example` should ship with the connection string commented out and a placeholder in its place:**

```bash
GEMINI_API_KEY=your_api_key_here
LOG_LEVEL=INFO

# Uncomment and set to use MySQL/RDS. Leave unset to use the local SQLite default.
# DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/<database>
```

The real credential currently embedded in `.env.example` should be treated as compromised — rotate it at the RDS instance level regardless of whether this repository is public or private, since it has already been persisted in an archive that left the original development environment.

---

## Phase 6: Local Execution & Deployment Bootstrap

### 6.1 Prerequisites — Apply Open Fixes First

Before following the startup sequence below, apply the two schema/code fixes from Phase 5 that block a fully healthy dual-process run:

1. Add the `worker_status` table to `app/files/alerts_schema.sql` (§5.3.1).
2. Add the `scan_memory` singleton to the end of `app/orchestration/scan_memory.py` (§5.3.2).

Skipping these does not prevent the API Gateway from running — it prevents the Engine Worker from persisting failure state and prevents any Sentinel-mode code path from importing successfully.

### 6.2 Environment Setup

```bash
# 1. Create and activate a Python 3.13 environment
conda create -n derivinsight python=3.13
conda activate derivinsight

# 2. Install all declared dependencies
pip install -r requirements.txt

# 3. Explicitly verify Redis is importable in THIS environment —
#    this has previously failed at worker runtime despite being declared
#    in requirements.txt, indicating an environment-sync gap rather than
#    a missing declaration.
python -c "import redis; print('redis OK:', redis.__version__)"

# 4. Verify the remaining AI/orchestration dependencies resolve cleanly
python -c "import langgraph, langchain, sqlglot, google.generativeai; print('core deps OK')"
```

### 6.3 Environment Configuration

```bash
cp .env.example .env
```

Then edit `.env` directly — do **not** rely on the copied file's default values for `DATABASE_URL` (see §5.3.4):

```bash
GEMINI_API_KEY=your_actual_key_here
LOG_LEVEL=INFO

# Leave DATABASE_URL unset/commented to run against local SQLite (recommended for first run):
# DATABASE_URL=sqlite:///./derivinsightnew.db

# Only uncomment if you have your own MySQL/RDS instance and credentials —
# never reuse a credential found in a shared or archived .env file:
# DATABASE_URL=mysql+pymysql://<your_user>:<your_password>@<your_host>:3306/<your_db>

# Redis is optional — omit entirely to run in fallback mode (§3.2 of this document):
# REDIS_URL=rediss://:<token>@<your-cluster-host>:6379/0
```

### 6.4 Database Initialization

If this is a first-time setup and neither SQLite file exists yet:

```bash
python -c "
from app.services.database import DatabaseService
db = DatabaseService()
db.initialize_db()   # applies app/files/derivinsight_schema.sql -> derivinsightnew.db
"
```

The alerts database (`derivinsight_alerts.db`) is initialized separately, on first Engine Worker start, via the schema-existence check in `app/workers/engine_worker.py`'s `main()`. Confirm the `worker_status` fix from §5.3.1 is present in `app/files/alerts_schema.sql` **before** this first run, since the schema file is only applied once at database-creation time — a fix added after the `.db` file already exists requires either deleting the file and re-initializing, or manually applying the `CREATE TABLE worker_status` statement against the existing database.

### 6.5 Pre-Flight Import Check (Sentinel Dependency Chain)

```bash
python -c "from app.orchestration.sentinel_agent import SentinelBrainstormer"
```

- **Clean exit, no output:** the `scan_memory` singleton is correctly wired; safe to proceed to worker startup.
- **`ImportError: cannot import name 'scan_memory'`:** the fix in §5.3.2 has not been applied. Do not proceed to §6.6 until resolved — the Engine Worker's process will otherwise crash immediately on its first orchestration-layer import.

### 6.6 Startup — Dual (or Triple) Terminal

**Terminal 1 — API Gateway:**

```bash
python -m uvicorn app.main:app --reload --port 8080
```

Confirms healthy boot when the log shows, in order:

```
Starting NL2SQL Pipeline on port 8080...
DatabaseService initialized with engine: ./derivinsightnew.db
LLM Service initialized with Gemini provider, model: gemini-3-flash-preview
```

**Terminal 2 — Background Alert Worker:**

```bash
python -m app.workers.engine_worker
```

**Terminal 3 (optional, only if exercising the synthetic event pipeline) — Event Generator Worker:**

```bash
python -m app.workers.generator_worker
```

Note the asymmetry documented in §5.3.3: if this process crashes, it currently produces no `FAILED` row and no structured log — watch its raw stdout/stderr directly rather than relying on `worker_status` for this specific worker until the fix is applied.

### 6.7 Verification Checklist

| # | Check | Command / URL | Expected Result |
|---|---|---|---|
| 1 | API liveness | `curl http://localhost:8080/health` | `{"status": "healthy"}` — note this does **not** confirm DB or LLM connectivity, only that the ASGI process is up (§2.2) |
| 2 | API documentation | `http://localhost:8080/docs` | Interactive OpenAPI UI renders with all six routers' endpoints listed |
| 3 | Frontend | `http://localhost:8080/` | Sentinel dashboard HTML loads directly (served from `frontend/index.html`, not a redirect) |
| 4 | Primary database reachable | `curl -X POST http://localhost:8080/api/v1/query -H "Content-Type: application/json" -d '{"question": "how many users are there"}'` | A synthesized response referencing a row count from `users`, not a 500 |
| 5 | Alerts database schema | `sqlite3 derivinsight_alerts.db ".tables"` | Lists `events`, `metric_specs`, `alert_history`, `anomaly_history`, `metric_windows`, `dashboards`, and — once §5.3.1 is applied — `worker_status` |
| 6 | Engine Worker health | `sqlite3 derivinsight_alerts.db "SELECT * FROM worker_status WHERE worker_name='engine';"` | A row with `status != 'FAILED'` and a recent `updated_at`; this check is only meaningful after §5.3.1 is applied |
| 7 | Sentinel import chain | `python -c "from app.orchestration.sentinel_agent import SentinelBrainstormer"` | Clean exit, confirms §5.3.2 is applied |
| 8 | Test suite (optional but recommended) | `pytest tests/` | `test_alert_engine.py`, `test_database.py`, `test_intent_classification.py`, `test_services.py`, `test_sql_generation.py`, and `test_workflow.py` all pass — a red `test_alert_engine.py` after applying §5.3.1 is the fastest signal that the `worker_status` schema change was written incorrectly |
