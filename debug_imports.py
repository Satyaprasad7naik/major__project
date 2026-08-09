import sys
import os

# Set PYTHONPATH
sys.path.append(os.getcwd())

try:
    print("Importing FastAPI...")
    from fastapi import FastAPI
    print("OK")

    print("Importing app.core.config...")
    from app.core.config import settings
    print("OK")

    print("Importing app.core.logger...")
    from app.core.logger import logger
    print("OK")

    print("Importing app.api.endpoints...")
    from app.api.endpoints import router as api_router
    print("OK")

    print("Importing app.api.alerts_endpoints...")
    from app.api.alerts_endpoints import router as alerts_router
    print("OK")

    print("Importing app.api.dashboard_endpoints...")
    from app.api.dashboard_endpoints import router as dashboard_router
    print("OK")

    print("Importing app.api.db_test_endpoints...")
    from app.api.db_test_endpoints import router as db_test_router
    print("OK")

    print("Importing app.api.sentinel...")
    from app.api.sentinel import router as sentinel_router
    print("OK")

    print("Importing app.api.redis_test_endpoints...")
    from app.api.redis_test_endpoints import router as redis_test_router
    print("OK")

    print("All imports SUCCESSFUL")
except Exception as e:
    print(f"FAILED with error: {e}")
    import traceback
    traceback.print_exc()
