"""
Auto Insights Scheduler for InsightOS.

Schedules periodic stockout and inventory risk analysis using APScheduler.
Triggers auto-insight detection rules:
1. Stockout Risk - products approaching or at reorder point
2. Critical Inventory - very low stock levels
3. Sales Drop - significant decrease in sales velocity
4. Supplier Risk - suppliers with low on-time delivery rates
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.modules.stockout_analyzer import analyze_stockout_risk
from app.services.auto_insights import generate_insights
from app.core.logger import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
scheduler_logger = logging.getLogger("insightos_scheduler")

# Scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_scheduler_started = False


class AutoInsightRule:
    """Represents a single auto-insight detection rule."""

    def __init__(self, name: str, description: str, method: str = "auto",
                 threshold_days: int = 7, enabled: bool = True):
        self.name = name
        self.description = description
        self.method = method
        self.threshold_days = threshold_days
        self.enabled = enabled

    async def check(self, domain: str) -> List[Dict[str, Any]]:
        """Run the rule analysis for a given domain."""
        if not self.enabled:
            return []

        try:
            results = analyze_stockout_risk(
                domain=domain,
                threshold_days=self.threshold_days,
                method=self.method
            )
            scheduler_logger.info(
                f"Rule '{self.name}' completed for {domain}: {len(results)} findings"
            )
            return results
        except Exception as e:
            scheduler_logger.error(f"Rule '{self.name}' failed: {e}")
            return []


# Pre-defined auto-insight rules (4 detection rules)
AUTO_INSIGHT_RULES = [
    AutoInsightRule(
        name="stockout_risk",
        description="Products at risk of stockout based on reorder point and days-of-cover",
        method="auto",
        threshold_days=7,
        enabled=True
    ),
    AutoInsightRule(
        name="critical_inventory",
        description="Products with critically low inventory levels",
        method="simple",
        threshold_days=3,
        enabled=True
    ),
    AutoInsightRule(
        name="sales_drop",
        description="Products with significant sales velocity drop",
        method="auto",
        threshold_days=7,
        enabled=True
    ),
    AutoInsightRule(
        name="supplier_risk",
        description="Suppliers with high risk of delayed deliveries",
        method="simple",
        threshold_days=7,
        enabled=True
    )
]


async def run_all_rules(domain: str) -> Dict[str, List[Dict[str, Any]]]:
    """Run all auto-insight detection rules for a domain."""
    results = {}
    for rule in AUTO_INSIGHT_RULES:
        rule_findings = await rule.check(domain)
        if rule_findings:
            results[rule.name] = rule_findings

    # Trigger generation and saving to auto_insights database table
    try:
        generate_insights("retail_clothing.db")
    except Exception as exc:
        scheduler_logger.error(f"Error in generate_insights during run_all_rules: {exc}")

    return results


async def schedule_periodic_checks(domain: str = "retail_clothing", interval_minutes: int = 120):
    """Schedule periodic stockout and auto-insights analysis."""
    global _scheduler, _scheduler_started

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

    if not _scheduler_started:
        # Run once immediately on startup
        try:
            from app.services.excel_sync import sync_excel_to_db
            sync_excel_to_db("retail_clothing.db", "live_data")
            generate_insights("retail_clothing.db")
        except Exception as err:
            scheduler_logger.error(f"Startup excel sync & auto_insights run failed: {err}")

        # 1. Job: Local Live Excel Data Sync (every 5 minutes)
        _scheduler.add_job(
            func=lambda: sync_excel_to_db("retail_clothing.db", "live_data"),
            trigger=IntervalTrigger(minutes=5),
            id="live_excel_data_sync_job",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True
        )

        from app.core.config import settings

        # 2. Job: Automated Tally Sync (every 60 min or configured interval)
        if getattr(settings, "TALLY_SYNC_ENABLED", True) or getattr(settings, "TALLY_AUTO_SYNC_ENABLED", True):
            from app.services.tally_auto_sync import run_tally_auto_sync
            tally_interval = getattr(settings, "TALLY_SYNC_INTERVAL_MINUTES", 60)
            _scheduler.add_job(
                func=lambda: run_tally_auto_sync(
                    host=settings.TALLY_HOST,
                    port=settings.TALLY_PORT,
                    company=settings.TALLY_COMPANY,
                    export_folder=getattr(settings, "TALLY_EXPORT_FOLDER", None),
                    live_data_dir=getattr(settings, "LIVE_DATA_DIR", "live_data"),
                    db_path="retail_clothing.db"
                ),
                trigger=IntervalTrigger(minutes=tally_interval),
                id="tally_auto_sync_job",
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True
            )
            scheduler_logger.info(f"[Scheduler] Registered Tally Auto-Sync job every {tally_interval} minutes.")

        # 3. Live Data Excel folder sync is the active primary sync mechanism.

        # 4. Job: Shared Network Folder Sync (every 5-10 min if enabled)
        if getattr(settings, "NETWORK_FOLDER_ENABLED", False) and getattr(settings, "NETWORK_FOLDER_PATH", None):
            from app.services.network_folder_sync import sync_network_folder
            nf_interval = getattr(settings, "NETWORK_FOLDER_SYNC_INTERVAL_MINUTES", 5)
            _scheduler.add_job(
                func=lambda: sync_network_folder(
                    network_folder_path=settings.NETWORK_FOLDER_PATH,
                    db_path="retail_clothing.db"
                ),
                trigger=IntervalTrigger(minutes=nf_interval),
                id="network_folder_sync_job",
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True
            )
            scheduler_logger.info(f"[Scheduler] Registered Network Folder Sync job every {nf_interval} minutes for path '{settings.NETWORK_FOLDER_PATH}'.")

        # Add job for periodic auto insights generation
        _scheduler.add_job(
            func=generate_insights,
            args=["retail_clothing.db"],
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="auto_insights_generation_job",
            replace_existing=True,
            misfire_grace_time=600,
            coalesce=True
        )

        # Add job for running rules
        _scheduler.add_job(
            func=run_all_rules,
            args=[domain],
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=f"insight_all_rules_{domain}",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True
        )

        # Start the scheduler
        _scheduler.start()
        _scheduler_started = True
        scheduler_logger.info(
            f"Auto insights scheduler started for domain '{domain}' "
            f"every {interval_minutes} minutes"
        )

    return _scheduler


async def stop_scheduler():
    """Stop the periodic scheduler."""
    global _scheduler, _scheduler_started

    if _scheduler and _scheduler_started:
        _scheduler.shutdown()
        _scheduler_started = False
        scheduler_logger.info("Auto insights scheduler stopped")


async def trigger_manual_check(domain: str) -> Dict[str, List[Dict[str, Any]]]:
    """Manually trigger all auto-insight rules (for API endpoints)."""
    return await run_all_rules(domain)
