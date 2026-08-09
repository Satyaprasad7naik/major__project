# """
# Scan Memory - Persistent scan history for adaptive mission intelligence.
# Tracks past missions, domain severity distribution, and critical findings
# so the brainstormer can adapt future scans.

# Also provides full scan persistence for the history viewer.
# """
# import json
# import os
# import glob as globmod
# from datetime import datetime
# from collections import Counter

# MEMORY_FILE = "sentinel_scan_history.json"
# SCAN_HISTORY_DIR = "scan_history"


# class ScanMemory:

#     MAX_HISTORY = 50

#     def __init__(self):
#         self.history = self._load()

#     def _load(self) -> list:
#         if os.path.exists(MEMORY_FILE):
#             try:
#                 with open(MEMORY_FILE, "r") as f:
#                     return json.load(f)
#             except Exception:
#                 return []
#         return []

#     def _save(self):
#         try:
#             with open(MEMORY_FILE, "w") as f:
#                 json.dump(self.history[-self.MAX_HISTORY :], f, indent=2, default=str)
#         except Exception as e:
#             print(f"Failed to save scan memory: {e}")

#     def record_scan(self, detections: list):
#         scan_record = {
#             "timestamp": datetime.utcnow().isoformat(),
#             "missions": [],
#             "domain_scores": {},
#             "critical_domains": [],
#         }

#         domain_scores = {}
#         for det in detections:
#             domain = det.get("domain", "general")
#             risk_score = det.get("risk_score", 0)

#             scan_record["missions"].append(
#                 {
#                     "name": det.get("mission_name"),
#                     "query": det.get("original_query", ""),
#                     "domain": domain,
#                     "risk_score": risk_score,
#                     "severity": det.get("severity"),
#                     "data_count": det.get("data_count", 0),
#                 }
#             )

#             if domain not in domain_scores:
#                 domain_scores[domain] = []
#             domain_scores[domain].append(risk_score)

#             if det.get("severity") == "CRITICAL":
#                 if domain not in scan_record["critical_domains"]:
#                     scan_record["critical_domains"].append(domain)

#         scan_record["domain_scores"] = {
#             d: round(sum(s) / len(s)) for d, s in domain_scores.items()
#         }

#         self.history.append(scan_record)
#         self._save()

#     def get_adaptive_context(self) -> dict:
#         if not self.history:
#             return {
#                 "domain_weights": {"security": 2, "compliance": 2, "risk": 2, "operations": 2},
#                 "avoid_queries": [],
#                 "focus_areas": [],
#                 "scan_count": 0,
#             }

#         recent = self.history[-5:]

#         # Domain weights: higher risk → more missions (base 2, max 4)
#         domain_avg_scores = Counter()
#         domain_counts = Counter()
#         for scan in recent:
#             for d, score in scan.get("domain_scores", {}).items():
#                 domain_avg_scores[d] += score
#                 domain_counts[d] += 1

#         domain_weights = {}
#         for domain in ["security", "compliance", "risk", "operations"]:
#             avg = domain_avg_scores.get(domain, 0) / max(domain_counts.get(domain, 1), 1)
#             domain_weights[domain] = min(4, max(1, round(2 + avg / 40)))

#         # Avoid repeating recent queries
#         recent_queries = []
#         for scan in recent[-3:]:
#             for m in scan.get("missions", []):
#                 q = m.get("query", "")
#                 if q and q not in recent_queries:
#                     recent_queries.append(q)

#         # Focus areas from critical findings in last scan
#         focus_areas = []
#         if recent:
#             last_scan = recent[-1]
#             for m in last_scan.get("missions", []):
#                 if m.get("severity") == "CRITICAL":
#                     focus_areas.append(
#                         f"CRITICAL finding in {m['domain']}: '{m['name']}' "
#                         f"(risk score {m['risk_score']}). Generate deeper variations."
#                     )

#         return {
#             "domain_weights": domain_weights,
#             "avoid_queries": recent_queries[-15:],
#             "focus_areas": focus_areas,
#             "scan_count": len(self.history),
#         }

#     # ─── Full Scan Persistence (for history viewer) ──────────────────────────

#     def save_full_scan(self, scan_id: str, detections: list,
#                        clusters: list = None, narrative: dict = None):
#         """Persist complete scan results to a per-scan JSON file."""
#         os.makedirs(SCAN_HISTORY_DIR, exist_ok=True)

#         critical_count = sum(1 for d in detections if d.get("severity") == "CRITICAL")
#         high_count = sum(1 for d in detections if d.get("severity") == "HIGH")
#         top_scores = sorted([d.get("risk_score", 0) for d in detections], reverse=True)
#         overall_risk = round(sum(top_scores[:3]) / max(len(top_scores[:3]), 1))

#         if narrative and narrative.get("overall_risk"):
#             overall_risk = narrative["overall_risk"]

#         overall_severity = "LOW"
#         if critical_count > 0:
#             overall_severity = "CRITICAL"
#         elif high_count > 0:
#             overall_severity = "HIGH"

#         data = {
#             "scan_id": scan_id,
#             "timestamp": datetime.utcnow().isoformat(),
#             "stats": {
#                 "total_missions": len(detections),
#                 "critical_count": critical_count,
#                 "high_count": high_count,
#                 "overall_risk": overall_risk,
#                 "overall_severity": overall_severity,
#             },
#             "detections": detections,
#             "clusters": clusters or [],
#             "narrative": narrative,
#         }

#         filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
#         try:
#             with open(filepath, "w") as f:
#                 json.dump(data, f, indent=2, default=str)
#         except Exception as e:
#             print(f"Failed to save full scan: {e}")

#         # Enforce cap
#         self._prune_old_scans()

#     def _prune_old_scans(self):
#         """Keep only the most recent MAX_HISTORY scan files."""
#         files = sorted(globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")))
#         if len(files) > self.MAX_HISTORY:
#             for old in files[: len(files) - self.MAX_HISTORY]:
#                 try:
#                     os.remove(old)
#                 except Exception:
#                     pass

#     def list_scans(self) -> list:
#         """Return metadata for all persisted scans, newest first."""
#         if not os.path.isdir(SCAN_HISTORY_DIR):
#             return []

#         scans = []
#         for filepath in globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")):
#             try:
#                 with open(filepath, "r") as f:
#                     data = json.load(f)
#                 scans.append({
#                     "scan_id": data["scan_id"],
#                     "timestamp": data["timestamp"],
#                     **data.get("stats", {}),
#                 })
#             except Exception:
#                 continue

#         scans.sort(key=lambda s: s["timestamp"], reverse=True)
#         return scans

#     def get_scan(self, scan_id: str) -> dict | None:
#         """Load full scan data by ID."""
#         filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
#         if not os.path.exists(filepath):
#             return None
#         try:
#             with open(filepath, "r") as f:
#                 return json.load(f)
#         except Exception:
#             return None

import json
import os
import uuid
import time
import glob as globmod
from datetime import datetime
from collections import Counter

SESSION_STORE_DIR = "scan_memory_sessions"
SESSION_TTL_SECONDS = 60 * 60 * 6  # 6 hours
SCAN_HISTORY_DIR = "scan_history"


class SessionScopedScanMemory:
    """
    One instance per session_id. Each session's history lives in its own
    file, keyed by a UUID, so no tenant can read or influence another's
    adaptive context.
    """

    MAX_HISTORY = 50

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        os.makedirs(SESSION_STORE_DIR, exist_ok=True)
        self._path = os.path.join(SESSION_STORE_DIR, f"{self.session_id}.json")
        self.history = self._load()

    def _load(self) -> list:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    payload = json.load(f)
                if time.time() - payload.get("_last_touched", 0) > SESSION_TTL_SECONDS:
                    return []
                return payload.get("history", [])
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self) -> None:
        payload = {"_last_touched": time.time(), "history": self.history[-self.MAX_HISTORY:]}
        with open(self._path, "w") as f:
            json.dump(payload, f, indent=2, default=str)

    def record_scan(self, detections: list) -> None:
        scan_record = {"timestamp": datetime.utcnow().isoformat(), "missions": [], "domain_scores": {}, "critical_domains": []}
        domain_scores: dict[str, list[int]] = {}
        for det in detections:
            domain = det.get("domain", "general")
            risk_score = det.get("risk_score", 0)
            scan_record["missions"].append({
                "name": det.get("mission_name"), "query": det.get("original_query", ""),
                "domain": domain, "risk_score": risk_score,
                "severity": det.get("severity"), "data_count": det.get("data_count", 0),
            })
            domain_scores.setdefault(domain, []).append(risk_score)
            if det.get("severity") == "CRITICAL" and domain not in scan_record["critical_domains"]:
                scan_record["critical_domains"].append(domain)
        scan_record["domain_scores"] = {d: round(sum(s) / len(s)) for d, s in domain_scores.items()}
        self.history.append(scan_record)
        self._save()

    @staticmethod
    def evict_expired_sessions() -> int:
        if not os.path.exists(SESSION_STORE_DIR):
            return 0
        evicted = 0
        cutoff = time.time() - SESSION_TTL_SECONDS
        for fname in os.listdir(SESSION_STORE_DIR):
            fpath = os.path.join(SESSION_STORE_DIR, fname)
            try:
                with open(fpath) as f:
                    if json.load(f).get("_last_touched", 0) < cutoff:
                        os.remove(fpath)
                        evicted += 1
            except (json.JSONDecodeError, OSError):
                os.remove(fpath)
                evicted += 1
        return evicted

    def get_adaptive_context(self) -> dict:
        if not self.history:
            return {
                "domain_weights": {"security": 2, "compliance": 2, "risk": 2, "operations": 2},
                "avoid_queries": [],
                "focus_areas": [],
                "scan_count": 0,
            }

        recent = self.history[-5:]
        domain_avg_scores = Counter()
        domain_counts = Counter()
        for scan in recent:
            for d, score in scan.get("domain_scores", {}).items():
                domain_avg_scores[d] += score
                domain_counts[d] += 1

        domain_weights = {}
        for domain in ["security", "compliance", "risk", "operations", "retail_clothing"]:
            avg = domain_avg_scores.get(domain, 0) / max(domain_counts.get(domain, 1), 1)
            domain_weights[domain] = min(4, max(1, round(2 + avg / 40)))

        recent_queries = []
        for scan in recent[-3:]:
            for m in scan.get("missions", []):
                q = m.get("query", "")
                if q and q not in recent_queries:
                    recent_queries.append(q)

        focus_areas = []
        if recent:
            last_scan = recent[-1]
            for m in last_scan.get("missions", []):
                if m.get("severity") == "CRITICAL":
                    focus_areas.append(
                        f"CRITICAL finding in {m['domain']}: '{m['name']}' "
                        f"(risk score {m['risk_score']}). Generate deeper variations."
                    )

        return {
            "domain_weights": domain_weights,
            "avoid_queries": recent_queries[-15:],
            "focus_areas": focus_areas,
            "scan_count": len(self.history),
        }

    # ─── Full Scan Persistence (for history viewer) ──────────────────────────

    def save_full_scan(self, scan_id: str, detections: list, clusters: list = None, narrative: dict = None):
        os.makedirs(SCAN_HISTORY_DIR, exist_ok=True)
        critical_count = sum(1 for d in detections if d.get("severity") == "CRITICAL")
        high_count = sum(1 for d in detections if d.get("severity") == "HIGH")
        top_scores = sorted([d.get("risk_score", 0) for d in detections], reverse=True)
        overall_risk = round(sum(top_scores[:3]) / max(len(top_scores[:3]), 1))

        if narrative and narrative.get("overall_risk"):
            overall_risk = narrative["overall_risk"]

        overall_severity = "LOW"
        if critical_count > 0:
            overall_severity = "CRITICAL"
        elif high_count > 0:
            overall_severity = "HIGH"

        data = {
            "scan_id": scan_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stats": {
                "total_missions": len(detections),
                "critical_count": critical_count,
                "high_count": high_count,
                "overall_risk": overall_risk,
                "overall_severity": overall_severity,
            },
            "detections": detections,
            "clusters": clusters or [],
            "narrative": narrative,
        }

        filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Failed to save full scan: {e}")

        self._prune_old_scans()

    def _prune_old_scans(self):
        files = sorted(globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")))
        if len(files) > self.MAX_HISTORY:
            for old in files[: len(files) - self.MAX_HISTORY]:
                try:
                    os.remove(old)
                except Exception:
                    pass

    def list_scans(self) -> list:
        if not os.path.isdir(SCAN_HISTORY_DIR):
            return []
        scans = []
        for filepath in globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                scans.append({
                    "scan_id": data["scan_id"],
                    "timestamp": data["timestamp"],
                    **data.get("stats", {}),
                })
            except Exception:
                continue
        scans.sort(key=lambda s: s["timestamp"], reverse=True)
        return scans

    def get_scan(self, scan_id: str) -> dict | None:
        filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return None

# Module-level singleton — imported by name in sentinel_agent.py and any
# other module that needs a shared, process-local default session.
scan_memory = SessionScopedScanMemory()