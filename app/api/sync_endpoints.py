"""
Advanced Automated Data Synchronization API Endpoints for InsightOS.
Supports:
1. Local live_data/ Excel Sync
2. Automated Tally ERP / TallyPrime Sync (Folder Watch & HTTP XML Server)
3. Google Sheets Live Sync (Service Account API & HTTP CSV Mode)
4. Shared Network Folder Sync (UNC Paths & Mapped Network Drives)
5. Unified Status Monitoring across all sources
"""

import sqlite3
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.services.excel_sync import sync_excel_to_db, get_sync_status, init_sync_schema
from app.services.tally_sync import (
    sync_tally_xml_to_db,
    ping_tally_server,
    auto_sync_tally,
    export_tally_to_excel_files,
    parse_tally_xml
)
from app.services.tally_auto_sync import run_tally_auto_sync, sync_tally_export_folder
from app.services.google_sheets_sync import sync_google_sheets
from app.services.network_folder_sync import sync_network_folder
from app.services.auto_insights import get_db_connection
from app.core.config import settings
from app.core.logger import logger

router = APIRouter(prefix="/sync", tags=["live-sync"])


def _extract_str(val: Any, default_val: str) -> str:
    """Extract string value from FastAPI Query parameter or default."""
    if isinstance(val, str):
        return val
    if hasattr(val, "default") and isinstance(val.default, str):
        return val.default
    return default_val


# ─────────────────────────────────────────────────────────────────────────────
# 1. Local Excel Sync Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/now", response_model=dict)
async def trigger_manual_sync(
    db_path: str = Query("retail_clothing.db", description="Database file path"),
    live_data_dir: str = Query("live_data", description="Directory with Excel files"),
):
    """
    Manually trigger Live Data Synchronization from Excel files in live_data/.
    Processes new/modified files and updates SQLite database tables.
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    clean_dir = _extract_str(live_data_dir, "live_data")

    logger.info(f"Manual sync requested for db: {clean_db}, dir: {clean_dir}")
    try:
        res = sync_excel_to_db(db_path=clean_db, live_data_dir=clean_dir, force=True)
        from app.services.auto_insights import generate_insights
        insights = generate_insights(clean_db)
        if isinstance(res, dict):
            res["insights_generated"] = len(insights)
        return res
    except Exception as exc:
        logger.error(f"Manual sync failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", response_model=dict)
async def fetch_sync_status(
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """
    Get current Live Data Sync status, last sync timestamp, and recent execution history.
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    try:
        return get_sync_status(db_path=clean_db)
    except Exception as exc:
        logger.error(f"Fetch sync status failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Automated Tally Sync Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tally/ping", response_model=dict)
async def check_tally_connection(
    host: str = Query(None, description="Tally host (default from config)"),
    port: int = Query(None, description="Tally port (default 9000)"),
):
    """
    Ping Tally ERP 9 / TallyPrime XML Server to verify if port is open and accessible.
    """
    t_host = host or settings.TALLY_HOST
    t_port = port or settings.TALLY_PORT
    return ping_tally_server(host=t_host, port=t_port)


@router.post("/tally/auto", response_model=dict)
@router.post("/tally/auto-pull", response_model=dict)
async def trigger_tally_auto_sync(
    host: str = Query(None, description="Tally host (default from config)"),
    port: int = Query(None, description="Tally port (default 9000)"),
    company: Optional[str] = Query(None, description="Tally Company Name"),
    export_folder: Optional[str] = Query(None, description="Tally export folder (optional)"),
    live_data_dir: str = Query("live_data", description="Target live_data directory"),
    db_path: str = Query("retail_clothing.db", description="Target database path"),
):
    """
    Trigger automated synchronization from Tally:
    Checks export folder first; falls back to live HTTP XML Server pull (Port 9000).
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    clean_dir = _extract_str(live_data_dir, "live_data")

    try:
        return run_tally_auto_sync(
            host=host or settings.TALLY_HOST,
            port=port or settings.TALLY_PORT,
            company=company or settings.TALLY_COMPANY,
            export_folder=export_folder or settings.TALLY_EXPORT_FOLDER,
            live_data_dir=clean_dir,
            db_path=clean_db,
            force=True
        )
    except Exception as exc:
        logger.error(f"Tally automated sync failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/tally/export-excel", response_model=dict)
async def convert_tally_xml_to_excel(
    xml_content: str = Body(..., media_type="application/xml", description="Raw Tally XML payload"),
    live_data_dir: str = Query("live_data", description="Target live_data directory"),
):
    """
    Convert raw Tally XML payload directly into Excel files in live_data/ folder.
    """
    clean_dir = _extract_str(live_data_dir, "live_data")
    try:
        parsed = parse_tally_xml(xml_content)
        res = export_tally_to_excel_files(parsed, live_data_dir=clean_dir)
        return res
    except Exception as exc:
        logger.error(f"Converting Tally XML to Excel failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tally/xml", response_model=dict)
async def ingest_tally_xml(
    xml_content: str = Body(..., media_type="application/xml", description="Raw Tally XML export payload"),
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """
    Directly ingest Tally ERP 9 / TallyPrime XML export payload into database.
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    logger.info("Direct Tally XML ingestion payload received")
    try:
        return sync_tally_xml_to_db(xml_content, db_path=clean_db)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error(f"Tally XML ingestion failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Google Sheets Live Sync Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSheetsSyncBody(BaseModel):
    sheet_id: Optional[str] = None
    credentials_file: Optional[str] = None
    db_path: Optional[str] = "retail_clothing.db"
    sheet_names: Optional[List[str]] = None


@router.post("/google-sheets", response_model=dict)
async def trigger_google_sheets_sync(
    body: Optional[GoogleSheetsSyncBody] = Body(None),
    sheet_id: Optional[str] = Query(None, description="Google Sheet ID (defaults to GOOGLE_SHEET_ID env var)"),
    credentials_file: Optional[str] = Query(None, description="Path to Service Account JSON (optional)"),
    db_path: str = Query("retail_clothing.db", description="Target database path"),
):
    """
    Trigger live data synchronization from a Google Sheet containing Products, Inventory, and Sales.
    """
    req_sheet_id = (body.sheet_id if body and body.sheet_id else None) or sheet_id or settings.GOOGLE_SHEET_ID
    req_creds = (body.credentials_file if body and body.credentials_file else None) or credentials_file or settings.GOOGLE_CREDENTIALS_FILE
    req_db = _extract_str((body.db_path if body and body.db_path else None) or db_path, "retail_clothing.db")
    req_sheets = (body.sheet_names if body and body.sheet_names else None)

    if not req_sheet_id:
        raise HTTPException(
            status_code=400,
            detail="Google Sheet ID is required. Pass in JSON body or ?sheet_id=... or configure GOOGLE_SHEET_ID in .env"
        )

    try:
        res = sync_google_sheets(
            sheet_id=req_sheet_id,
            credentials_file=req_creds,
            db_path=req_db,
            sheet_names=req_sheets
        )
        return res
    except Exception as exc:
        logger.error(f"Google Sheets sync failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/google-sheets/auth-url", response_model=dict)
async def get_google_sheets_auth_url(
    client_id: Optional[str] = Query(None, description="Google OAuth Client ID (optional override)"),
    redirect_uri: Optional[str] = Query(None, description="Google OAuth Redirect URI (optional override)"),
):
    """
    Generate Google OAuth 2.0 authorization URL for user consent (Method B: Google Sign-In).
    """
    from app.services.google_sheets_sync import get_google_oauth_auth_url
    url = get_google_oauth_auth_url(client_id=client_id, redirect_uri=redirect_uri)
    return {
        "auth_url": url,
        "instructions": "Open this URL in your browser, grant Google Drive/Sheets read access, and copy the authorization code to /connect endpoint."
    }


@router.post("/google-sheets/connect", response_model=dict)
async def connect_google_account(
    auth_code: str = Body(..., embed=True, description="Authorization code from Google OAuth consent"),
    client_id: Optional[str] = Body(None, description="Google OAuth Client ID (optional)"),
    client_secret: Optional[str] = Body(None, description="Google OAuth Client Secret (optional)"),
):
    """
    Exchange Google OAuth authorization code for tokens and store them securely for live sync.
    """
    from app.services.google_sheets_sync import handle_google_oauth_callback
    try:
        tokens = handle_google_oauth_callback(
            auth_code=auth_code,
            client_id=client_id,
            client_secret=client_secret
        )
        return {
            "status": "CONNECTED",
            "message": "Google account connected successfully! User OAuth tokens stored for automated live sync.",
            "token_type": tokens.get("token_type"),
            "expires_in": tokens.get("expires_in")
        }
    except Exception as exc:
        logger.error(f"Google OAuth connection failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/google-sheets/oauth-callback")
async def google_sheets_oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    error: Optional[str] = Query(None, description="OAuth error code if consent denied"),
):
    """
    Callback handler for Google OAuth redirect flow.
    """
    if error:
        return {"status": "ERROR", "message": f"Google authorization was denied or failed: {error}"}
    if not code:
        return {"status": "ERROR", "message": "No authorization code received from Google."}

    from app.services.google_sheets_sync import handle_google_oauth_callback
    try:
        handle_google_oauth_callback(auth_code=code)
        return {
            "status": "SUCCESS",
            "message": "Google account connected successfully! InsightOS can now sync your Google Sheets in the background."
        }
    except Exception as exc:
        return {"status": "FAILED", "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Shared Network Folder Sync Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/network-folder", response_model=dict)
async def trigger_network_folder_sync(
    folder_path: Optional[str] = Query(None, description="Network folder UNC path or mapped drive"),
    db_path: str = Query("retail_clothing.db", description="Target database path"),
):
    """
    Trigger live synchronization from a shared network folder (e.g. \\\\server\\share\\data).
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    target_path = folder_path or settings.NETWORK_FOLDER_PATH

    if not target_path:
        raise HTTPException(
            status_code=400,
            detail="Network folder path is required. Pass ?folder_path=... or configure NETWORK_FOLDER_PATH in .env"
        )

    try:
        res = sync_network_folder(
            network_folder_path=target_path,
            db_path=clean_db,
            force=True
        )
        return res
    except Exception as exc:
        logger.error(f"Network folder sync failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Unified Multi-Source Status Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status/all", response_model=dict)
async def fetch_all_sync_statuses(
    db_path: str = Query("retail_clothing.db", description="Database file path"),
):
    """
    Returns comprehensive status, configuration, and last sync timestamp across all sources:
    1. Local Excel Sync (live_data/)
    2. Tally ERP / TallyPrime
    3. Google Sheets
    4. Shared Network Folder
    5. Recent Sync Log History
    """
    clean_db = _extract_str(db_path, "retail_clothing.db")
    conn = get_db_connection(clean_db)
    init_sync_schema(conn)
    cursor = conn.cursor()

    # Query last sync per source type
    sources = ["EXCEL", "TALLY", "TALLY_FOLDER", "GOOGLE_SHEETS", "NETWORK_FOLDER"]
    source_statuses = {}

    for src in sources:
        row = cursor.execute("""
            SELECT status, rows_synced, synced_at, file_name, error_message
            FROM sync_logs
            WHERE source_type LIKE ? OR source_type = ?
            ORDER BY id DESC
            LIMIT 1
        """, (f"{src}%", src)).fetchone()

        if row:
            source_statuses[src] = {
                "configured": True,
                "last_status": row[0],
                "last_rows_synced": row[1],
                "last_synced_at": str(row[2]),
                "last_target": row[3],
                "last_error": row[4]
            }
        else:
            source_statuses[src] = {
                "configured": False,
                "last_status": "NEVER_RUN",
                "last_rows_synced": 0,
                "last_synced_at": None,
                "last_target": None,
                "last_error": None
            }

    # Fetch 15 most recent logs
    recent_logs = cursor.execute("""
        SELECT source_type, file_name, status, rows_synced, synced_at, error_message
        FROM sync_logs
        ORDER BY id DESC
        LIMIT 15
    """).fetchall()

    conn.close()

    history = []
    for r in recent_logs:
        history.append({
            "source_type": r[0],
            "file_name": r[1],
            "status": r[2],
            "rows_synced": r[3],
            "synced_at": str(r[4]),
            "error_message": r[5]
        })

    return {
        "status": "ok",
        "configuration": {
            "tally": {
                "enabled": settings.TALLY_SYNC_ENABLED,
                "host": settings.TALLY_HOST,
                "port": settings.TALLY_PORT,
                "export_folder": settings.TALLY_EXPORT_FOLDER,
                "interval_minutes": settings.TALLY_SYNC_INTERVAL_MINUTES
            },
            "google_sheets": {
                "enabled": settings.GOOGLE_SHEETS_ENABLED,
                "sheet_id": settings.GOOGLE_SHEET_ID,
                "credentials_file": settings.GOOGLE_CREDENTIALS_FILE,
                "interval_minutes": settings.GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES
            },
            "network_folder": {
                "enabled": settings.NETWORK_FOLDER_ENABLED,
                "path": settings.NETWORK_FOLDER_PATH,
                "interval_minutes": settings.NETWORK_FOLDER_SYNC_INTERVAL_MINUTES
            },
            "local_excel": {
                "directory": getattr(settings, "LIVE_DATA_DIR", "live_data")
            }
        },
        "sources": source_statuses,
        "recent_logs": history
    }
