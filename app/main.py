from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.endpoints import router as api_router
from app.api.alerts_endpoints import router as alerts_router
from app.api.dashboard_endpoints import router as dashboard_router
from app.api.db_test_endpoints import router as db_test_router
from app.api.sentinel import router as sentinel_router
from app.api.redis_test_endpoints import router as redis_test_router
from app.api.insights_endpoints import router as insights_router
from app.api.stockout_endpoints import router as stockout_router
from app.api.auth import router as auth_router
from app.api.pricing_endpoints import router as pricing_router
from app.api.supply_chain_endpoints import router as supply_chain_router
from app.api.carbon_endpoints import router as carbon_router
from app.api.sync_endpoints import router as sync_router
from app.api.purchase_order_endpoints import router as po_router
from app.api.procurement_endpoints import router as procurement_router
from app.api.chat_endpoints import router as chat_router
from app.api.forecast_endpoints import router as forecast_router
from app.api.invoice_endpoints import router as invoice_router
from app.modules.scheduler import schedule_periodic_checks, stop_scheduler, trigger_manual_check
from app.core.config import settings
from app.core.logger import logger
import os

app = FastAPI(title=settings.PROJECT_NAME)
logger.info(f"Starting {settings.PROJECT_NAME} on port 8080...")

import traceback
from fastapi import Request
from fastapi.responses import JSONResponse

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on FastAPI startup."""
    # Ensure live_data directory exists
    live_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live_data")
    os.makedirs(live_data_dir, exist_ok=True)

    await schedule_periodic_checks(
        domain=settings.DEFAULT_DOMAIN or "retail_clothing",
        interval_minutes=settings.SCHEDULER_INTERVAL_MINUTES or 60
    )
    # Run auto_insights migration to ensure table exists
    from app.migrations.migration_002_auto_insights import run_all_migrations
    run_all_migrations()

    # Load custom AI models
    try:
        from app.ml_models.model_manager import model_manager
        model_manager.load_all_models()
        logger.info("Custom AI models initialized successfully.")
    except Exception as e:
        logger.warning(f"Could not initialize custom ML models at startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up scheduler on FastAPI shutdown."""
    await stop_scheduler()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"GLOBAL EXCEPTION CAUGHT: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# Enable CORS — origins controlled via ALLOWED_ORIGINS env var.
# Default: localhost development origins. Never use * in production with allow_credentials=True.
_allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)          # JWT authentication — public
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(alerts_router)        # Alerts API endpoints
app.include_router(dashboard_router)     # Dashboard API endpoints
app.include_router(db_test_router)       # Database testing endpoints
app.include_router(sentinel_router, prefix="/api/v1/sentinel", tags=["sentinel"])
app.include_router(insights_router, prefix=settings.API_V1_STR)      # Insights API (/api/v1/insights)
app.include_router(insights_router)                                    # Direct Insights API (/insights)
app.include_router(po_router, prefix=settings.API_V1_STR)            # PO API (/api/v1/purchase-orders)
app.include_router(po_router)                                          # Direct PO API (/purchase-orders)
app.include_router(redis_test_router)    # Redis/Valkey connectivity test
app.include_router(pricing_router)       # Dynamic Pricing Engine
app.include_router(supply_chain_router)  # Supply Chain & Inventory
app.include_router(carbon_router)        # Carbon Accounting (Scope 1-3)
app.include_router(stockout_router)      # Stockout analysis endpoints
app.include_router(sync_router, prefix=settings.API_V1_STR)          # Live Data Sync (Excel + Tally)
app.include_router(procurement_router, prefix=settings.API_V1_STR)     # Autonomous Procurement Agent
app.include_router(chat_router, prefix=settings.API_V1_STR)            # Chat with Your Data (NL2SQL)
app.include_router(forecast_router, prefix=settings.API_V1_STR)        # CNN-LSTM Demand Forecasting
app.include_router(invoice_router, prefix=settings.API_V1_STR)         # Multimodal Invoice Ingestion

@app.get("/health")
def health_check():
    """
    Readiness probe — checks DB connectivity and custom AI models availability.
    Returns 200 with probe results when healthy, 503 when degraded.
    """
    from app.services.database import DatabaseService

    probes: dict = {"api": "ok"}

    # Primary database probe
    try:
        db = DatabaseService()
        db.execute_query("SELECT 1")
        probes["database"] = "ok"
    except Exception as exc:
        probes["database"] = f"error: {exc}"

    # Custom ML Models probe
    try:
        from app.ml_models.model_manager import model_manager
        probes["custom_models"] = model_manager.get_model_status()
    except Exception as exc:
        probes["custom_models"] = f"error: {exc}"

    overall = "healthy" if probes["database"] == "ok" else "degraded"
    status_code = 200 if overall == "healthy" else 503
    return JSONResponse(content={"status": overall, "probes": probes}, status_code=status_code)

# Serve frontend static files — prioritize vanilla frontend (cyber theme)
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    def serve_frontend():
        """Serve the vanilla frontend HTML"""
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/styles.css")
    def serve_styles():
        return FileResponse(os.path.join(frontend_path, "styles.css"), media_type="text/css")

    @app.get("/script.js")
    def serve_script():
        return FileResponse(os.path.join(frontend_path, "script.js"), media_type="application/javascript")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
