# """
# Alert Engine Worker
# ====================
# Runs the alert engine loop in the foreground. Intended to run in a dedicated container.
# Register this container's task ARN via POST /api/v1/alerts/engine/start with body {"task_arn": "<arn>"}
# or have the API start the task via ECS and store the taskArn in Redis.
# """

# import os
# import signal
# import sys

# # Ensure app is on path when run as script
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# from app.services.alert_engine import AlertEngineService, ALERTS_DB_PATH


# def main():
#     schema_path = os.path.join(
#         os.path.dirname(__file__), "..", "files", "alerts_schema.sql"
#     )
#     if not os.path.exists(ALERTS_DB_PATH) and os.path.exists(schema_path):
#         engine = AlertEngineService()
#         engine.initialize_db(schema_path)
#     elif not os.path.exists(ALERTS_DB_PATH):
#         print("[EngineWorker] DB and schema not found; exiting.", file=sys.stderr)
#         sys.exit(1)

#     engine = AlertEngineService()
#     tick_interval = float(os.environ.get("ENGINE_TICK_INTERVAL", "1.0"))

#     def on_stop(signum=None, frame=None):
#         print("[EngineWorker] Shutdown requested, stopping engine...")
#         engine.stop()

#     signal.signal(signal.SIGTERM, on_stop)
#     signal.signal(signal.SIGINT, on_stop)

#     print("[EngineWorker] Starting alert engine loop (tick_interval=%s)" % tick_interval)
#     # engine.run_engine(tick_interval=tick_interval)
#     try:
#         engine.run_engine(tick_interval=tick_interval)
#     except Exception as e:
#         print(f"FATAL WORKER ERROR: {e}")
#         # Force the system to log the failure before dying
#         if hasattr(engine, "db"):
#             engine.db.execute("UPDATE worker_status SET status = 'FAILED'")
#     print("[EngineWorker] Stopped.")


# if __name__ == "__main__":
#     main()
# import time
# from app.core.logger import logger

# def start_worker(tick_interval: int = 5):
#     """
#     Background worker process that continuously runs the scanning engine.
#     Includes exception handling to prevent silent background crashes.
#     """
#     logger.info("Starting Engine Background Worker...")
    
#     while True:
#         try:
#             from app.services.alert_engine import alert_engine
#             # Run background scan tick
#             alert_engine.run_engine_tick()
#         except Exception as e:
#             logger.error(f"FATAL WORKER ERROR: {str(e)}")
#             # Log error state safely so worker recovers on next tick
#             time.sleep(tick_interval)
#         else:
#             time.sleep(tick_interval)

# if __name__ == "__main__":
#     start_worker()
# import time
# import sys
# from app.core.logger import logger

# def start_worker(tick_interval: int = 5):
#     """
#     Background worker process that continuously runs the scanning engine.
#     Includes exception handling to prevent silent background crashes.
#     """
#     logger.info(f"Starting Engine Background Worker (tick_interval={tick_interval})...")
    
#     while True:
#         try:
#             from app.services.alert_engine import alert_engine
#             # Run background scan tick
#             alert_engine.run_engine_tick()
#         except Exception as e:
#             logger.error(f"FATAL WORKER ERROR: {str(e)}", exc_info=True)
            
#             # Phase 5: Persist FAILED state so the dashboard knows the worker died
#             try:
#                 from app.services.alert_engine import alert_engine
#                 if hasattr(alert_engine, "mark_worker_failed"):
#                     alert_engine.mark_worker_failed(reason=str(e))
#             except Exception as mark_exc:
#                 logger.error(f"Could not persist FAILED state: {mark_exc}")
            
#             # Exit process after logging failure so container/supervisor can restart it
#             sys.exit(1)
#         else:
#             time.sleep(tick_interval)

# if __name__ == "__main__":
#     start_worker()

import time
import sys
import os
import signal
from app.core.logger import logger
from app.services.alert_engine import AlertEngineService, ALERTS_DB_PATH

def main():
    # 1. Initialize schema if it doesn't exist
    schema_path = os.path.join(os.path.dirname(__file__), "..", "files", "alerts_schema.sql")
    if not os.path.exists(ALERTS_DB_PATH) and os.path.exists(schema_path):
        engine = AlertEngineService()
        engine.initialize_db(schema_path)
    elif not os.path.exists(ALERTS_DB_PATH):
        print("[EngineWorker] DB and schema not found; exiting.", file=sys.stderr)
        sys.exit(1)

    engine = AlertEngineService()
    tick_interval = float(os.environ.get("ENGINE_TICK_INTERVAL", "5.0"))

    def on_stop(signum=None, frame=None):
        print("[EngineWorker] Shutdown requested, stopping engine...")
        engine.stop()

    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)

    print(f"[EngineWorker] Starting alert engine loop (tick_interval={tick_interval})")
    try:
        # 2. Run the main engine loop (Phase 5 Spec)
        engine.run_engine(tick_interval=tick_interval)
    except Exception as exc:
        logger.error(f"[EngineWorker] Fatal error in engine loop: {exc}", exc_info=True)
        try:
            # 3. Mark worker as failed in the database
            engine.mark_worker_failed(reason=str(exc))
        except Exception as mark_exc:
            logger.error(f"[EngineWorker] Could not persist FAILED state: {mark_exc}")
        sys.exit(1)
    print("[EngineWorker] Stopped.")

if __name__ == "__main__":
    main()