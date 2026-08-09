# DerivInsight: Enterprise Architectural Handoff & State Matrix (Part 2)

**System:** DerivInsight (Internal branding: **InsightOS**)
**Document Type:** Engineering Source of Truth
**Audience:** Senior engineers onboarding to backend, orchestration, or infrastructure work
**Scope of this document:** Phase 3 — Resilience & Failover, Phase 4 — AI & Domain Intelligence, Phase 5 — Incident Ledger

---

## Phase 3: Resilience & Circuit Breakers

### 3.1 Redis Fallback & Circuit Breaker

The system expects an optional Redis cache for tracking ECS worker Task ARNs (`REDIS_KEY_ENGINE_TASK_ARN` and `REDIS_KEY_GENERATOR_TASK_ARN`), defined in `app/services/worker_registry.py`.

To prevent a Redis outage from taking down the core API or the worker synchronization processes, a deliberate fallback mechanism acts as an application-level circuit breaker:
- `WorkerRegistry._init_redis()` wraps the connection logic in a safe `try/except` block catching `TimeoutError`, `ConnectionError`, and `RedisError`.
- If the configured `REDIS_URL` is unreachable or times out (timeout limits are strictly capped at 3.0s), the registry gracefully downgrades `self._client` to `None`.
- Downstream methods (`set_engine_task_arn`, `get_engine_task_arn`, etc.) check for `self.redis` availability and return `False` or `None` instead of throwing unhandled exceptions.
- **Impact**: Redis being down silently degrades task tracking, but keeps the API and engine fully operational.

### 3.2 Database Configuration Fallback

The primary database target is set by `DATABASE_URL` in `app/core/config.py`.
- If `DATABASE_URL` is omitted from the environment, the system defaults to the local file-based database `sqlite:///./derivinsightnew.db`.
- This ensures local setups and containerized testing can run instantly without requiring a separate PostgreSQL or MySQL container up front.
- Similarly, `SCHEMA_PATH` defaults to `app/files/derivinsight_schema.sql` to initialize local data dynamically.

---

## Phase 4: AI Prompt Engineering & Adaptive Sentinel Weights

### 4.1 Domain-Scoped Prompts

The system relies on LLMs for both generating SQL queries (Reactive Mode) and brainstorming autonomous security missions (Proactive Mode). 
In `app/orchestration/sentinel_agent.py`, the `SentinelBrainstormer` injects the explicit database schema (`users`, `transactions`, `login_events`) dynamically into the prompt.
- The prompt strictly defines the domain focus: **security**, **compliance**, **operations**, and **risk**.
- It forces the output format to be a strictly parsed JSON list containing `id`, `name`, `query`, `domain`, and `severity`.

### 4.2 Adaptive Domain-Weighting Formula

The Sentinel Agent does not perform a static round-robin across domains. Instead, it features an **adaptive domain-weighting formula**:
- Gated by the `ADAPTIVE_ENABLED` feature flag (default: `True`) in `config.py`.
- It fetches previous scan context via `scan_memory.get_adaptive_context()`.
- If `scan_count > 0`, the system automatically retrieves historical `domain_weights`, `focus_areas`, and `avoid_queries`.
- This creates a self-reinforcing feedback loop. If the previous scan found a high number of critical anomalies in the `security` domain, the domain weights adjust to allocate more brainstormed missions to `security` in the subsequent scan.
- The prompt restricts the LLM from repeating `avoid_queries` to ensure horizontal scanning coverage and prevents it from infinitely repeating the exact same audit mission.

---

## Phase 5: Incident Ledger & Open Defect Tracking

### 5.1 Documented Incident: Background Worker Silent Failure

**Defect ID:** 2026-ENG-001 (Worker Status Sync)
**Component:** `app/workers/engine_worker.py`
**Description:** 
Historically, if the `run_engine` polling loop inside the background worker encountered a fatal exception (e.g., malformed database connection or invalid JSON response from the LLM), the worker would crash silently in the background. Because the API Gateway runs in a separate process/container, it was unaware of this failure, and the frontend dashboard would indefinitely show the engine as running without any new missions being scanned.

**Resolution / Current State:**
The exception handling in `engine_worker.py` was explicitly hardened (marked as "Phase 5 Spec"). 
1. The `try/except` block catching the exception now invokes `engine.mark_worker_failed(reason=str(exc))`.
2. This synchronizes the failure state to the database (`worker_status = 'FAILED'`).
3. The process deliberately calls `sys.exit(1)`, forcing the container orchestrator (e.g., ECS or local supervisor) to recognize the crash and initiate a restart.
4. The dashboard correctly reflects the worker crash state to the end user by querying the persisted `FAILED` state.
