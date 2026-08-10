# Task: Migrate InsightOS from Trading Domain → Retail Clothing Domain (Option A: Full Swap)

**Repo:** `M_PROJECT-main`
**Decision:** Option A — full swap. The retail_clothing domain becomes the *only* active domain. The trading/security domain (`users`, `transactions`, `login_events`) is retired and backed up, not deleted.

This document is a self-contained execution spec. Follow it in order. Each step lists the file(s) to touch, the exact change, and how to verify it worked.

---

## 0. Inputs already provided

These 5 files are the new data source and should be placed as follows before any code changes:

| File | Destination |
|---|---|
| `retail_clothing.db` | project root |
| `products.csv` | `app/files/seed_data/products.csv` |
| `suppliers.csv` | `app/files/seed_data/suppliers.csv` |
| `inventory.csv` | `app/files/seed_data/inventory.csv` |
| `sales_events.csv` | `app/files/seed_data/sales_events.csv` |

`retail_clothing.db` schema (already verified against the CSVs — identical):
- `products(sku PK, style_name, category, size, color, unit_cost, retail_price, supplier_id, created_at)` — 120 rows
- `inventory(sku, location, stock_count, reorder_point, last_restocked_at)` — 120 rows
- `suppliers(supplier_id PK, supplier_name, lead_time_days, on_time_rate, country)` — 6 rows
- `sales_events(event_id PK, sku, units_sold, sale_date, channel)` — 328 rows

---

## 1. Back up and swap the database

```bash
# from repo root
mv derivinsightnew.db derivinsightnew.trading_backup.db
cp <path-to-uploaded>/retail_clothing.db ./retail_clothing.db

# generate the matching schema file the app expects at boot
sqlite3 retail_clothing.db .schema > app/files/retail_clothing_schema.sql
```

Do **not** delete `derivinsightnew.trading_backup.db` — keep it in the repo (or `.gitignore` it and keep locally) as a rollback path.

## 2. Point the app config at the new DB/schema

**File:** `app/core/config.py`

Change:
```python
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./derivinsightnew.db")
SCHEMA_PATH: str = os.getenv("SCHEMA_PATH", "app/files/derivinsight_schema.sql")
```
to:
```python
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./retail_clothing.db")
SCHEMA_PATH: str = os.getenv("SCHEMA_PATH", "app/files/retail_clothing_schema.sql")
```

Also add/update `.env` (or `.env.example`) with the same two values so local runs pick it up without relying on the default.

**Verify:** app boots and a raw `sqlite3 ./retail_clothing.db "SELECT COUNT(*) FROM products;"` returns 120.

## 3. Fix the Sentinel autonomous scan planner

**File:** `app/orchestration/sentinel_agent.py`

Find:
```python
domain_weights = {"security": count_per_domain, "compliance": count_per_domain,
                   "risk": count_per_domain, "operations": count_per_domain}
```
Replace with:
```python
domain_weights = {"retail_clothing": count_per_domain}
```
Also grep the same file for any other literal references to `security`, `compliance`, `risk`, or `operations` as domain keys (e.g. in prompt templates that enumerate "MISSION ALLOCATION BY DOMAIN") and update them to describe only `retail_clothing`, using the vocabulary from `app/data/domains/retail_clothing.json` (dead stock, sizing anomaly, supplier delay).

**Verify:** triggering a Sentinel scan produces missions whose `domain` field is `retail_clothing` and whose queries reference `products`/`inventory`/`suppliers`/`sales_events` only.

## 4. Reconcile the duplicate domain-prompt config

There are two sources of domain prompts:
- `app/data/domains/*.json` (already correct — `retail_clothing.json` is complete)
- `app/modules/preprocessing/assets/domain_config.py` → `DOMAIN_PROMPTS` dict (older, trading-only: `security`, `compliance`, `risk`, `operations`, `general` — **no `retail_clothing` entry**)

Steps:
1. Grep the codebase for `DOMAIN_PROMPTS` and `domain_config` imports to find which modules actually read this dict at runtime (e.g. intent classification, SQL generation).
2. If `domain_config.py` is live code (not dead/legacy), add a `"retail_clothing"` key to `DOMAIN_PROMPTS` using the `prompts.intent` and `prompts.sql` text from `app/data/domains/retail_clothing.json`, and delete or comment out the `security`/`compliance`/`risk`/`operations`/`general` entries.
3. If `domain_config.py` is dead code superseded by the JSON loader, remove it (or leave a `# DEPRECATED — superseded by app/data/domains/*.json` comment) rather than maintaining two sources of truth.

**Verify:** a natural-language query like "show me dead stock older than 90 days" is classified with intent domain `retail_clothing` and produces the SQL from the few-shot in `retail_clothing.json`.

## 5. Add alert engine metric specs for the 3 retail rules

**File:** `app/files/alerts_schema.sql` (schema) + a seed/migration for the `metric_specs` table

Add three `metric_specs` rows, mirroring the structure of the existing trading rows, for:
1. **Dead stock** — `stock_count > 0` AND no `sales_events` row for that `sku` in the last 90 days.
2. **Sizing anomaly** — a size's `stock_count` deviates more than 2x from the average `stock_count` of other sizes within the same `style_name`.
3. **Supplier delay** — `suppliers.lead_time_days` exceeds the category average, OR `on_time_rate < 0.85`.

Use the exact SQL patterns already given as few-shots in `app/data/domains/retail_clothing.json` as the basis for each `metric_specs.query` (or equivalent field — check the `alert_rules`/`metric_specs` table definition for the exact column the engine reads).

**Verify:** running the alert engine (`run_alerts_engine.py` or the worker) against the new DB produces at least one alert per rule (dead stock and sizing anomaly should both fire against the sample data — confirm by manually running the underlying SELECTs first).

## 6. Update tests

**Files:** `tests/test_database.py`, `tests/test_sql_generation.py`, `tests/test_alert_engine.py`, `tests/test_workflow.py`

These currently assert against `users`/`transactions`/`login_events` table names and trading-domain sample queries. Update fixtures and assertions to use `products`/`inventory`/`suppliers`/`sales_events` and retail_clothing few-shots instead. Run the full suite after:

```bash
pytest tests/ -v
```

Fix failures one file at a time rather than mass-rewriting — some tests (e.g. Redis fallback, worker crash handling in `test_workflow.py`) are domain-agnostic and should be left alone.

## 7. Frontend/copy sweep (do last, cosmetic)

**Files:** `README.md`, `frontend/index.html`, `frontend/script.js`, `frontend-react/src/components/ChatInterface.tsx`, `frontend-react/src/components/SentinelDashboard.tsx`, `frontend-react/src/components/Sidebar.tsx`

Replace trading-specific copy ("DerivInsight", "Virtual CIO for Real-Time Financial Intelligence", KYC/transaction language) with retail-appropriate copy. This has no functional effect — do it only after steps 1–6 are verified working, and treat it as polish, not correctness.

---

## Acceptance criteria (definition of done)

- [ ] App boots against `retail_clothing.db` with no reference to the old schema anywhere in the default config path.
- [ ] A Sentinel autonomous scan generates only `retail_clothing`-domain missions.
- [ ] Natural-language retail queries (dead stock, sizing anomaly, supplier delay, "show sales by channel") return correct SQL and results.
- [ ] At least the dead-stock and sizing-anomaly alert rules fire against the sample data.
- [ ] `pytest tests/` passes (or documented remaining failures are pre-existing/unrelated).
- [ ] `derivinsightnew.trading_backup.db` still exists and is untouched, as a rollback path.
