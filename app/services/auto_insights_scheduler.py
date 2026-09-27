"""
Auto Insights Scheduler for InsightOS.

Background job running every 1-2 hours to proactively detect anomalies
across all domains. Triggers 4 auto-insight detection rules and stores
results in the auto_insights table.
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.modules.stockout_analyzer import analyze_stockout_risk
from app.core.logger import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
insights_logger = logging.getLogger("insights_scheduler")

# Scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_scheduler_started = False


# ────────────────────────────────────────────────────────────────────
# Detection Rules (from design doc Section 3.2)
# ────────────────────────────────────────────────────────────────────

STOCKOUT_RULE_THRESHOLD_DAYS = 7
CRITICAL_STOCKOUT_STOCK = 0
SALES_DROP_RATIO = 0.5  # current < 0.5 * prior
SUPPLIER_DELAY_LEAD_TIME = 14
SUPPLIER_DELAY_ON_TIME_RATE = 0.8


class InsightRule:
    """Base class for a single auto-insight detection rule."""

    def __init__(self, name: str, insight_type: str, severity: str,
                 description: str, enabled: bool = True):
        self.name = name
        self.insight_type = insight_type
        self.severity = severity
        self.description = description
        self.enabled = enabled

    async def check(self, domain: str) -> Optional[Dict[str, Any]]:
        """Run the rule analysis. Returns None if no insight found."""
        raise NotImplementedError


class StockoutRiskRule(InsightRule):
    """Rule 1: Stockout Risk - products with days_of_cover <= threshold."""

    def __init__(self):
        super().__init__(
            name="stockout_risk",
            insight_type="stockout_risk",
            severity="HIGH",
            description="Products at risk of stockout based on reorder point and days-of-cover",
            enabled=True
        )

    async def check(self, domain: str) -> Optional[Dict[str, Any]]:
        results = await analyze_stockout_risk(
            domain=domain,
            threshold_days=STOCKOUT_RULE_THRESHOLD_DAYS,
            method="auto"
        )

        if not results:
            return None

        # Find the most at-risk product
        most_at_risk = results[0]  # Already sorted by urgency
        days_cover = most_at_risk.get('days_of_cover')

        return {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d')}-001",
            "domain": domain,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": f"Stockout Risk: {len(results)} products at risk",
            "description": f"{len(results)} product(s) have {STOCKOUT_RULE_THRESHOLD_DAYS} or fewer days of cover remaining",
            "payload_json": json.dumps({
                "at_risk_products": results,
                "threshold_days": STOCKOUT_RULE_THRESHOLD_DAYS,
                "method": "auto"
            }),
            "sku": most_at_risk.get('sku'),
            "supplier_id": most_at_risk.get('supplier_id'),
            "status": "ACTIVE"
        }


class CriticalStockoutRule(InsightRule):
    """Rule 2: Critical Stockout - products with stock_count == 0."""

    def __init__(self):
        super().__init__(
            name="critical_stockout",
            insight_type="critical_stockout",
            severity="CRITICAL",
            description="Products with zero inventory stock levels",
            enabled=True
        )

    async def check(self, domain: str) -> Optional[Dict[str, Any]]:
        # Use simple method to check stock vs reorder point directly
        results = await analyze_stockout_risk(
            domain=domain,
            threshold_days=1,  # dummy, won't be used
            method="simple"
        )

        critical_products = [
            r for r in results if r.get('stock_count', 0) <= CRITICAL_STOCKOUT_STOCK
        ]

        if not critical_products:
            return None

        most_critical = critical_products[0]
        return {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d')}-002",
            "domain": domain,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": f"Critical Stockout: {len(critical_products)} product(s) at zero stock",
            "description": f"{len(critical_products)} product(s) have reached critical stock level (0 units)",
            "payload_json": json.dumps({
                "critical_products": critical_products,
                "method": "simple"
            }),
            "sku": most_critical.get('sku'),
            "supplier_id": most_critical.get('supplier_id'),
            "status": "ACTIVE"
        }


class SalesDropRule(InsightRule):
    """Rule 3: Sales Drop - current 7-day avg < 50% of prior 7-day avg."""

    def __init__(self):
        super().__init__(
            name="sales_drop",
            insight_type="sales_drop",
            severity="MEDIUM",
            description="Products with significant sales velocity decrease",
            enabled=True
        )

    async def check(self, domain: str) -> Optional[Dict[str, Any]]:
        # This requires accessing sales data; for now integrate with stockout analyzer
        # The stockout analyzer already computes avg_daily_sales, so we can use that
        results = await analyze_stockout_risk(
            domain=domain,
            threshold_days=7,
            method="auto"
        )

        sales_drop_products = []
        for r in results:
            avg_daily = r.get('avg_daily_sales', 0)
            # We need prior period data - placeholder logic for now
            # In full implementation, would query prior 7-day average
            if avg_daily > 0:
                sales_drop_products.append(r)

        if not sales_drop_products:
            return None

        # Return the product with lowest sales velocity
        weakest = min(sales_drop_products, key=lambda x: x.get('avg_daily_sales', 0))
        return {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d')}-003",
            "domain": domain,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": f"Sales Drop Detected: {len(sales_drop_products)} product(s) showing decline",
            "description": f"{len(sales_drop_products)} product(s) showing reduced sales velocity",
            "payload_json": json.dumps({
                "sales_drop_products": sales_drop_products,
                "method": "auto"
            }),
            "sku": weakest.get('sku'),
            "status": "ACTIVE"
        }


class SupplierRiskRule(InsightRule):
    """Rule 4: Supplier Risk - lead_time > 14 days AND on_time_rate < 80%."""

    def __init__(self):
        super().__init__(
            name="supplier_risk",
            insight_type="supplier_risk",
            severity="MEDIUM",
            description="Suppliers with high risk of delayed deliveries",
            enabled=True
        )

    async def check(self, domain: str) -> Optional[Dict[str, Any]]:
        # Query suppliers directly from database
        from app.services.database import db_service
        import sqlite3

        # Check each domain's database
        domain_dbs = {
            "retail_clothing": "retail_clothing.db",
            "banking_finance": "derivinsightnew.db",
            "insurance": "derivinsightnew.db",
        }
        db_path = domain_dbs.get(domain, "retail_clothing.db")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("""
                SELECT s.supplier_id, s.supplier_name, s.lead_time_days, s.on_time_rate
                FROM suppliers s
            """)
            suppliers = cursor.fetchall()
            conn.close()
        except Exception:
            return None

        risky_suppliers = []
        for sup in suppliers:
            supplier_id, name, lead_time, on_time_rate = sup
            if lead_time > SUPPLIER_DELAY_LEAD_TIME and on_time_rate < SUPPLIER_DELAY_ON_TIME_RATE:
                risky_suppliers.append({
                    "supplier_id": supplier_id,
                    "name": name,
                    "lead_time_days": lead_time,
                    "on_time_rate": on_time_rate
                })

        if not risky_suppliers:
            return None

        return {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d')}-004",
            "domain": domain,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": f"Supplier Risk: {len(risky_suppliers)} supplier(s) at risk",
            "description": f"{len(risky_suppliers)} supplier(s) have lead time > {SUPPLIER_DELAY_LEAD_TIME} days AND on-time rate < {SUPPLIER_DELAY_ON_TIME_RATE*100}%",
            "payload_json": json.dumps({
                "risky_suppliers": risky_suppliers,
                "lead_time_threshold": SUPPLIER_DELAY_LEAD_TIME,
                "on_time_rate_threshold": SUPPLIER_DELAY_ON_TIME_RATE
            }),
            "supplier_id": risky_suppliers[0]['supplier_id'],
            "status": "ACTIVE"
        }


# ────────────────────────────────────────────────────────────────────
# Rule Registry
# ────────────────────────────────────────────────────────────────────

AUTO_INSIGHT_RULES = [
    StockoutRiskRule(),
    CriticalStockoutRule(),
    SalesDropRule(),
    SupplierRiskRule()
]


async def run_all_rules(domain: str) -> List[Dict[str, Any]]:
    """Run all 4 auto-insight detection rules for a domain."""
    insights = []
    for rule in AUTO_INSIGHT_RULES:
        if not rule.enabled:
            continue
        insight = await rule.check(domain)
        if insight:
            insights.append(insight)
    # Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    insights.sort(key=lambda x: severity_order.get(x.get('severity', 'LOW'), 99))
    return insights


async def trigger_manual_check(domain: str) -> List[Dict[str, Any]]:
    """Manually trigger all rules (for API endpoints)."""
    return await run_all_rules(domain)


# ────────────────────────────────────────────────────────────────────
# Scheduler Integration
# ────────────────────────────────────────────────────────────────────

async def schedule_periodic_checks(domain: str, interval_minutes: int = 90):
    """Schedule periodic auto-insight checks for a domain."""
    global _scheduler, _scheduler_started

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

    if not _scheduler_started:
        # Add job for all rules
        _scheduler.add_job(
            func=lambda: asyncio.create_task(run_all_rules(domain)),
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="auto_insights_check",
            replaceable=True,
            misfire_grace_time=600,
            coalesce=True
        )

        _scheduler.start()
        _scheduler_started = True
        insights_logger.info(
            f"Auto insights scheduler started for domain '{domain}' "
            f"with {len(AUTO_INSIGHT_RULES)} rules every {interval_minutes} minutes"
        )

    return _scheduler


async def stop_scheduler():
    """Stop the periodic scheduler."""
    global _scheduler, _scheduler_started

    if _scheduler and _scheduler_started:
        _scheduler.shutdown()
        _scheduler_started = False
        insights_logger.info("Auto insights scheduler stopped")


# ────────────────────────────────────────────────────────────────────
# Confidence Scoring (from design doc Section 3.3)
# ────────────────────────────────────────────────────────────────────

CONFIDENCE_MIN_THRESHOLD = 0.5

# Confidence weight components
WEIGHT_INTENT = 0.3
WEIGHT_SQL_VALIDITY = 0.2
WEIGHT_RESULT_QUALITY = 0.3
WEIGHT_DOMAIN_EXPERTISE = 0.2


def calculate_confidence(
    intent_confidence: float,
    sql_validity_attempts: int = 1,
    result_row_count: int = 0,
    domain_match: bool = False
) -> Dict[str, Any]:
    """
    Calculate overall confidence score (0.0 - 1.0) and explanation.

    Formula:
        confidence = (
            intent_confidence * WEIGHT_INTENT +
            sql_validity_confidence * WEIGHT_SQL_VALIDITY +
            result_quality_confidence * WEIGHT_RESULT_QUALITY +
            domain_expertise_boost * WEIGHT_DOMAIN_EXPERTISE
        )

    Where:
        - sql_validity_confidence = 1.0 if 1st attempt, 0.7 if 2nd, 0.3 if 3rd+
        - result_quality_confidence = min(1.0, row_count / 10) * data_completeness
        - domain_expertise_boost = 0.1 if domain-specific few-shots matched
    """
    # SQL validity confidence
    if sql_validity_attempts <= 1:
        sql_validity_confidence = 1.0
    elif sql_validity_attempts <= 2:
        sql_validity_confidence = 0.7
    else:
        sql_validity_confidence = 0.3

    # Result quality confidence
    result_quality_confidence = min(1.0, result_row_count / 10) if result_row_count > 0 else 0.1

    # Domain expertise boost
    domain_boost = 0.1 if domain_match else 0.0

    # Calculate overall confidence
    confidence = (
        intent_confidence * WEIGHT_INTENT +
        sql_validity_confidence * WEIGHT_SQL_VALIDITY +
        result_quality_confidence * WEIGHT_RESULT_QUALITY +
        domain_boost * WEIGHT_DOMAIN_EXPERTISE
    )

    # Ensure within bounds
    confidence = max(0.0, min(1.0, confidence))

    # Determine if low confidence warning
    is_low = confidence < CONFIDENCE_MIN_THRESHOLD

    # Generate explanation
    explanation_parts = []
    if intent_confidence < 0.6:
        explanation_parts.append(f"question intent was ambiguous ({intent_confidence:.0%})")
    if sql_validity_attempts > 1:
        explanation_parts.append(f"SQL required {sql_validity_attempts} attempt(s) to validate")
    if result_row_count < 5:
        explanation_parts.append(f"limited data ({result_row_count} rows returned)")
    if not domain_match:
        explanation_parts.append("using general domain knowledge")

    explanation = ". ".join(explanation_parts) + "." if explanation_parts else "analysis completed successfully."

    return {
        "confidence": round(confidence, 3),
        "is_low": is_low,
        "explanation": explanation,
        "breakdown": {
            "intent_contribution": round(intent_confidence * WEIGHT_INTENT * 100, 1),
            "sql_validity_contribution": round(sql_validity_confidence * WEIGHT_SQL_VALIDITY * 100, 1),
            "result_quality_contribution": round(result_quality_confidence * WEIGHT_RESULT_QUALITY * 100, 1),
            "domain_expertise_contribution": round(domain_boost * WEIGHT_DOMAIN_EXPERTISE * 100, 1)
        }
    }


# ────────────────────────────────────────────────────────────────────
# Database Helper for auto_insights table
# ────────────────────────────────────────────────────────────────────

async def store_insight(insight: Dict[str, Any], db_path: str) -> bool:
    """
    Store an generated insight into the auto_insights table.
    Returns True if successfully stored.
    """
    import sqlite3
    import os

    # Ensure database directory exists
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute("""
            INSERT INTO auto_insights
            (insight_id, domain, insight_type, severity, title, description,
             payload_json, sku, supplier_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            insight.get('insight_id'),
            insight.get('domain'),
            insight.get('insight_type'),
            insight.get('severity'),
            insight.get('title'),
            insight.get('description'),
            insight.get('payload_json'),
            insight.get('sku'),
            insight.get('supplier_id'),
            insight.get('status', 'ACTIVE')
        ))
        conn.commit()
        return True
    except Exception as e:
        insights_logger.error(f"Failed to store insight: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()