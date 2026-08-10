# InsightOS → Retail Clothing Domain: File Placement & Migration Analysis

**Project:** InsightOS / DerivInsight / SentinelIQ (`M_PROJECT-main`)
**Goal:** Replace the trading/financial data currently powering the app with your new retail-clothing data (`products.csv`, `suppliers.csv`, `inventory.csv`, `sales_events.csv`, `retail_clothing.db`)
**Scope:** Where the files go, what already works, what's broken/missing, and the exact steps to finish the switch.

---

## 1. The good news: you already built half of this

I opened `app/data/domains/retail_clothing.json` and it's already a fully-written domain config — intent-classification prompt, SQL-generation prompt, and few-shot examples, scoped exactly to your four tables (`products`, `inventory`, `suppliers`, `sales_events`). It even defines domain-specific business rules ("dead stock" = 90 days no sale, "sizing anomaly" = 2x deviation, "supplier delay" = lead time above average or `on_time_rate < 0.85`).

So this isn't a from-scratch rebuild — it's finishing a migration you (or a past session) already started. The problem is the rest of the system was never pointed at it.

## 2. Where your 5 files go

| File | Destination | Why |
|---|---|---|
| `retail_clothing.db` | Project root, replacing (or alongside) `derivinsightnew.db` | This is a ready-made SQLite DB with the exact 4 tables (`products` 120 rows, `inventory` 120 rows, `suppliers` 6 rows, `sales_events` 328 rows) matching the domain config. It's the fastest path — see Option A below. |
| `products.csv` | `app/files/seed_data/products.csv` (new folder) | Source-of-truth CSV kept alongside the schema/mock-data scripts, so `generate_mock_data.py`-style tooling and anyone re-seeding the DB later can find it. |
| `suppliers.csv` | `app/files/seed_data/suppliers.csv` | Same reason. |
| `inventory.csv` | `app/files/seed_data/inventory.csv` | Same reason. |
| `sales_events.csv` | `app/files/seed_data/sales_events.csv` | Same reason. |

The CSVs and the `.db` are the same data (I verified the schema matches column-for-column), so you don't need to load both — keep the CSVs as the readable/editable source, and the `.db` as what the app actually queries.

## 3. Why nothing works yet even though the domain config exists

The app is wired for **one single database** at a time, via `app/core/config.py`:

```python
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./derivinsightnew.db")
SCHEMA_PATH: str = os.getenv("SCHEMA_PATH", "app/files/derivinsight_schema.sql")
```

`derivinsightnew.db` and `app/files/derivinsight_schema.sql` only define `users`, `transactions`, `login_events` (plus alert/audit tables) — pure trading/security schema. Your retail tables live nowhere the app currently points.

Three more places are still hardcoded to the old domain and will silently ignore retail_clothing even after you swap the DB:

1. **`app/orchestration/sentinel_agent.py`** — the autonomous scan planner's default mission allocation is:
   ```python
   domain_weights = {"security": count_per_domain, "compliance": count_per_domain,
                      "risk": count_per_domain, "operations": count_per_domain}
   ```
   `retail_clothing` is missing from this dict entirely, so the proactive "Sentinel" scans will never generate retail missions.

2. **`app/modules/preprocessing/assets/domain_config.py`** — a second, older copy of domain prompts (`DOMAIN_PROMPTS` dict) that predates the JSON files in `app/data/domains/`. It's unclear which one the live code path reads at runtime; both need to agree or one needs to be deleted.

3. **`app/files/alerts_schema.sql` / alert engine** — the anomaly-detection tables (`metric_specs`, `alert_history`, `anomaly_history`) were built around trading metrics (transaction velocity, KYC expiry, etc.). None of your retail business rules (dead stock, sizing anomaly, supplier delay) have corresponding `metric_specs` rows yet, so the alert engine won't flag anything in the clothing data even though the SQL layer can query it.

4. **Branding/copy** — `README.md`, `frontend/index.html`, `frontend/script.js`, and a few React components (`ChatInterface.tsx`, `SentinelDashboard.tsx`, `Sidebar.tsx`) reference "DerivInsight" / trading language. Cosmetic, but worth a pass if you're presenting this as a retail product.

## 4. Two ways to finish the switch

### Option A — Fast swap (recommended for you right now)
Point the whole app at your new DB and treat retail_clothing as the *only* domain. Best if you want a working retail demo quickly and don't need trading and retail side-by-side.

```bash
# 1. Back up the old db (optional but recommended)
mv derivinsightnew.db derivinsightnew.trading_backup.db

# 2. Drop your new db in as the primary target
cp /path/to/retail_clothing.db ./derivinsightnew.db
# or simply repoint the env var instead of renaming files:
```
`.env`:
```
DATABASE_URL=sqlite:///./retail_clothing.db
SCHEMA_PATH=app/files/retail_clothing_schema.sql
```
Then extract a `retail_clothing_schema.sql` from the db so re-seeding works the same way the trading schema does:
```bash
sqlite3 retail_clothing.db .schema > app/files/retail_clothing_schema.sql
```

Remaining code changes for Option A:
- In `sentinel_agent.py`, replace the hardcoded `domain_weights` dict with `{"retail_clothing": count_per_domain}` (or make it read from `app/data/domains/*.json` dynamically instead of hardcoding domain names — better long-term fix).
- Reconcile `domain_config.py` vs the JSON files so only one source of truth remains (delete the trading-only entries from `DOMAIN_PROMPTS` or replace them with the retail prompt).
- Write `metric_specs` rows for your 3 retail rules (dead stock, sizing anomaly, supplier delay) so the alert engine and dashboards have something to compute against — mirror the pattern used for the existing trading `metric_specs` rows in `alerts_schema.sql`.
- Update `frontend/index.html`, `script.js`, and the 3 React components flagged above to swap trading copy for retail copy.



## 5. Suggested order of operations

1. Copy the 5 files per the table in §2.
2. Do the DB swap (Option A commands above) and regenerate `retail_clothing_schema.sql`.
3. Fix `sentinel_agent.py` domain_weights.
4. Reconcile the two domain-prompt sources (`domain_config.py` vs `app/data/domains/*.json`).
5. Add `metric_specs` rows for dead stock / sizing anomaly / supplier delay so alerts actually fire.
6. Run `tests/test_database.py` and `tests/test_sql_generation.py` against the new schema — they currently assert against trading table names and will fail until updated.
7. Sweep frontend copy (optional, cosmetic).

## 6. What I did **not** yet change

I've only analyzed the codebase and prepared this plan — I haven't modified any files in the project yet, since a domain swap touches the DB, several Python modules, and test fixtures, and I wanted you to confirm which option (A or B) you want before I start editing. Let me know which direction you'd like and I'll make the actual code changes.
