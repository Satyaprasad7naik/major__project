## Phase 7: Consolidated Defect Registry & Live Verification Protocol

This phase exists for one reason: every prior phase describes the system as it is designed to work. This phase lists **everything actually wrong with it**, ranked by severity, in one place — and gives you a live, executable protocol to confirm each fix actually works, not just that the code looks right on the page.

### 7.1 Consolidated Defect Registry

Every item below was confirmed by direct source inspection (grep, full file reads, AST parsing, or `py_compile`), not inferred from documentation or assumed from the original project brief.

| # | Defect | Severity | Location | Status |
|---|---|---|---|---|
| 1 | `mark_worker_failed()` targets a `worker_status` table that is never created anywhere in the schema — fails silently, swallowed by its own `try/except` | **High** | `app/services/alert_engine.py`, `app/files/alerts_schema.sql` | Open — fix in §5.3.1 |
| 2 | `sentinel_agent.py` imports `scan_memory` by name; no module-level singleton exists in `scan_memory.py` — raises `ImportError`, blocks all Sentinel-mode code paths | **High** | `app/orchestration/scan_memory.py` | Open — fix in §5.3.2 |
| 3 | No authentication or authorization layer exists anywhere in the codebase — confirmed by a repo-wide search for `OAuth2PasswordBearer`, `JWT`, `jwt.encode/decode`, and `APIKeyHeader`, all returning zero matches | **High** | Entire `app/` tree | Open — no fix scoped in this document; required before any customer-facing deployment |
| 4 | No `customer_id`/tenant concept on any table — if a customer-facing layer is added on top of this engine, every query must be manually scoped or one customer will see another's data | **High** | `derivinsightnew.db` schema | Open — architectural gap, not a bug to patch in isolation |
| 5 | `.env.example` — the file new engineers are told to copy — contains a live, uncommented database credential; your actual working `.env` has the equivalent line commented out | **High** (hygiene) | `.env.example` | Open — fix in §5.3.4; rotate the exposed credential regardless of fix status |
| 6 | `generator_worker.py` has no exception boundary around `generator.start_all(...)` — a crash here produces a bare, unlogged traceback with no `worker_status` row, unlike `engine_worker.py` | **Medium** | `app/workers/generator_worker.py` | Open — fix in §5.3.3, depends on defect #1 being fixed first |
| 7 | `redis` has previously failed to import at worker runtime (`ModuleNotFoundError`) despite being correctly declared in `requirements.txt` — an environment-sync gap, confirmed via live application logs, not a code defect | **Medium** | Runtime environment | Open — re-verify with `pip install -r requirements.txt` before every worker deployment, not just initial setup |
| 8 | `CORS` middleware is configured with `allow_origins=["*"]`, `allow_credentials=True` — self-documented in code as a placeholder, but currently live | **Medium** | `app/main.py` | Open — must be scoped to real origins before any non-local deployment |
| 9 | `/health` returns `{"status": "healthy"}` unconditionally — it does not check database or LLM connectivity, so it cannot be relied on as a true readiness probe | **Medium** | `app/main.py` | Open — acceptable for a liveness check, insufficient as a readiness check; document the distinction for whoever wires this into an orchestrator's health check config |
| 10 | `db_test_endpoints.py`'s table-scoped routes (`/schema/{table_name}`, `/table/{table_name}`) — re-verified in this pass — **do** correctly validate `table_name` against `inspector.get_table_names()` before use | **N/A — confirmed non-issue** | `app/api/db_test_endpoints.py` | Not a defect; listed here only because an earlier phase of this audit raised it as a generic risk category before this endpoint specifically was inspected |
| 11 | `langchain-anthropic` is declared in `requirements.txt` but never imported or referenced anywhere in `app/` | **Low** | `requirements.txt` | Open — dead dependency; either wire it in as a real third provider or remove it to reduce install surface |
| 12 | `derivinsight_alerts.db`'s schema file is authored in MySQL dialect (`AUTO_INCREMENT`, `TINYINT(1)`) but is currently executed against SQLite | **Low / informational** | `app/files/alerts_schema.sql` | Not broken today — SQLite accepts this syntax permissively — but signals a MySQL migration was intended and never completed; worth a deliberate decision rather than leaving it ambiguous |
| 13 | The database "fallback" between MySQL and SQLite is a static, startup-time `os.getenv()` resolution, not a dynamic, latency-aware circuit breaker — a real risk only if anyone assumes the opposite when planning a production rollout | **Low / conceptual** | `app/core/config.py` | Not a bug — a documentation/expectation risk. Making this genuinely dynamic (a real health-check-driven failover) would be new work, not a fix. |

**Resolved, for completeness — do not re-open these:**

| Item | Verified Resolution |
|---|---|
| `database.py`'s `_execute_sql_file` previously committed partial batches on failure (bug found in an earlier snapshot of this codebase) | Now wrapped in an explicit `atomic_transaction()` context manager with `BEGIN`/`COMMIT`/`ROLLBACK` semantics — confirmed present in the current codebase. |
| `DATABASE_URL` was previously a hardcoded literal, bypassing environment configuration | Now reads via `os.getenv("DATABASE_URL", ...)` — confirmed. |
| `REDIS_HOST` previously defaulted to a literal AWS infrastructure hostname | Now defaults to `None`, with an in-code comment confirming this was a deliberate security fix. |
| Redis client operations previously called unsafe string methods (`.startswith()`) on potentially empty/`None` URLs | `_init_redis()` now guards with an explicit `if not self.redis_url:` check before any string operation. |

### 7.2 Live Verification Protocol

Everything above was confirmed through **static analysis** — reading source, parsing ASTs, grepping for patterns, compiling for syntax errors. None of it confirms the system behaves correctly under a real, running workload with real credentials. Run the following, in order, against your actual environment before treating any of this as "done."

**Step 1 — Confirm the environment actually has what `requirements.txt` claims it has.**

```bash
pip install -r requirements.txt
python -c "import redis, langchain, langgraph, sqlglot, google.generativeai, langchain_openai, pymysql, boto3; print('All core dependencies import cleanly')"
```

If this fails on `redis` specifically, that reproduces defect #7 directly — do not proceed until it passes.

**Step 2 — Apply the two High-severity code fixes, then confirm each one individually.**

```bash
# After adding the worker_status table to alerts_schema.sql and
# re-initializing (or migrating) derivinsight_alerts.db:
sqlite3 derivinsight_alerts.db ".schema worker_status"
# Expect: a CREATE TABLE statement to print. No output means the fix wasn't applied
# or wasn't applied to the database file actually in use.

# After adding the scan_memory singleton:
python -c "from app.orchestration.sentinel_agent import SentinelBrainstormer; print('Sentinel import chain OK')"
# Expect: clean print, no ImportError.
```

**Step 3 — Force a real worker failure and confirm it's actually recorded, not just logged.**

This is the step that separates "the code looks right" from "the code works." Temporarily break something the engine worker depends on — for example, rename `app/files/alerts_schema.sql` — then start the worker and watch both the process output and the database:

```bash
mv app/files/alerts_schema.sql app/files/alerts_schema.sql.bak
python -m app.workers.engine_worker
# Let it fail, then Ctrl+C if it doesn't exit on its own.
mv app/files/alerts_schema.sql.bak app/files/alerts_schema.sql

sqlite3 derivinsight_alerts.db "SELECT * FROM worker_status WHERE worker_name='engine';"
# Expect: a row with status='FAILED' and a populated last_error column.
# If this row doesn't exist or doesn't say FAILED, defect #1's fix did not
# actually take effect end-to-end, regardless of what the code looks like.
```

**Step 4 — Run the real test suite against the real environment.**

```bash
pytest tests/ -v
```

Pay particular attention to `test_alert_engine.py` — it is the test most likely to break or newly pass as a direct result of the `worker_status` schema change, since it exercises the alert engine's persistence layer most directly.

**Step 5 — Exercise both live modes end-to-end, not just their import paths.**

```bash
# Terminal 1
python -m uvicorn app.main:app --reload --port 8080

# Terminal 2
python -m app.workers.engine_worker

# From a third shell, exercise Reactive Mode:
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "how many users are there"}'
# Expect: a synthesized natural-language answer referencing an actual row count,
# not a 500 and not a generic fallback message.

# Exercise Proactive Mode:
curl http://localhost:8080/api/v1/sentinel/scan
# Expect: a real scan result referencing at least one of the five domains,
# not an immediate error — this specifically exercises the previously-broken
# scan_memory import chain under real request load, not just at process start.
```

**Step 6 — Only after all five steps above pass, treat the system as verified.**

At that point you have confirmed, empirically: dependencies resolve in the real environment, both High-severity fixes take effect end-to-end (not just at the code-review level), the test suite passes against the real schema, and both operating modes produce real output under a live request. That is the actual bar for "working," not a clean read-through of the source.

### 7.3 What Remains Genuinely Unverified Even After Step 6

Passing the protocol above confirms the system functions under a single, local, low-concurrency, happy-path run. It does **not** confirm:

- Behavior under concurrent multi-user load against the same SQLite files (§2.3's lock-contention reasoning is architectural intent, not a load-tested guarantee).
- Correct behavior of the Qubrid → OpenAI → Gemini provider fallback under an actual provider outage — Step 5 only exercises whichever provider succeeds first.
- Any of `correlation_engine.py`, `narrative_generator.py`, or `deep_dive.py`'s output quality — these were confirmed to exist and to be wired into the pipeline, not audited line-by-line for correctness.
- Frontend behavior — nothing in this entire audit touched `frontend/script.js` or `frontend-react/`.
- Anything related to the ECS Fargate deployment target described in §1.2 — the configuration exists; whether the actual AWS resources it references are provisioned and reachable was never checked, since that lives outside this codebase entirely.
