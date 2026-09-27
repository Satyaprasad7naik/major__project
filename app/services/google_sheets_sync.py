"""
Google Sheets Live Sync Service for InsightOS.
Provides automated data ingestion from Google Sheets into the InsightOS SQLite database.
Supports:
1. Google Cloud Service Account (credentials.json via gspread / google-auth) [Method A - Recommended]
2. User Google Sign-In / OAuth2 Token Storage (google_user_token.json) [Method B - User Connected]
3. Direct HTTP CSV Export URL ingestion (Zero-credential mode for link-shared sheets)
"""

import os
import io
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, List
import pandas as pd

from app.core.config import settings
from app.core.logger import logger
from app.services.auto_insights import generate_insights, get_db_connection
from app.services.excel_sync import (
    init_sync_schema,
    _upsert_products,
    _upsert_inventory,
    _upsert_sales
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. OAuth2 Helper Functions (Method B: Google Sign-In / User Connected)
# ─────────────────────────────────────────────────────────────────────────────

def get_google_oauth_auth_url(
    client_id: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    state: str = "insightos_gsheets"
) -> str:
    """Generate Google OAuth 2.0 authorization URL for user consent."""
    cid = client_id or settings.GOOGLE_CLIENT_ID or "YOUR_GOOGLE_CLIENT_ID"
    r_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    scopes = "https://www.googleapis.com/auth/spreadsheets.readonly https://www.googleapis.com/auth/drive.readonly"
    params = {
        "client_id": cid,
        "redirect_uri": r_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def handle_google_oauth_callback(
    auth_code: str,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    token_file: Optional[str] = None
) -> Dict[str, Any]:
    """Exchanges authorization code for access & refresh tokens and stores them securely."""
    cid = client_id or settings.GOOGLE_CLIENT_ID
    secret = client_secret or settings.GOOGLE_CLIENT_SECRET
    r_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    dest_file = token_file or settings.GOOGLE_OAUTH_TOKEN_FILE

    if not cid or not secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured for OAuth token exchange.")

    token_url = "https://oauth2.googleapis.com/token"
    payload = urllib.parse.urlencode({
        "code": auth_code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": r_uri,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))

    # Add timestamp and client info
    token_data["created_at"] = datetime.now().isoformat()
    token_data["client_id"] = cid

    save_user_oauth_token(token_data, dest_file)
    logger.info(f"[Google Sheets OAuth] User OAuth tokens saved securely to {dest_file}")
    return token_data


def save_user_oauth_token(token_data: Dict[str, Any], token_file: Optional[str] = None):
    """Save token data to secure local JSON file."""
    fpath = token_file or settings.GOOGLE_OAUTH_TOKEN_FILE
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)


def load_user_oauth_token(token_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load cached user OAuth token data."""
    fpath = token_file or settings.GOOGLE_OAUTH_TOKEN_FILE
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load Google OAuth token: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Worksheet Ingestion Engines
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sheet_via_http_csv(sheet_id: str, sheet_name: str, timeout: float = 10.0) -> pd.DataFrame:
    """
    Fetches a specific worksheet from a Google Sheet as CSV over HTTP without requiring credentials
    (works for sheets with link-sharing enabled: 'Anyone with the link can view').
    """
    encoded_name = urllib.parse.quote(sheet_name)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_name}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InsightOS/1.0"}
    )
    
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(content))
        return df


def fetch_sheet_via_service_account(
    sheet_id: str,
    credentials_file: str
) -> Dict[str, pd.DataFrame]:
    """
    Fetches all worksheets from a Google Sheet using Google Service Account credentials via gspread.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.warning("[Google Sheets Sync] gspread / google-auth not installed. Falling back to HTTP CSV method.")
        return {}

    if not os.path.exists(credentials_file):
        logger.warning(f"[Google Sheets Sync] Credentials file '{credentials_file}' not found.")
        return {}

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    gc = gspread.authorize(creds)
    
    spreadsheet = gc.open_by_key(sheet_id)
    result_sheets = {}
    for ws in spreadsheet.worksheets():
        data = ws.get_all_records()
        if data:
            result_sheets[ws.title] = pd.DataFrame(data)
            
    return result_sheets


def fetch_sheet_via_oauth_token(
    sheet_id: str,
    token_data: Dict[str, Any]
) -> Dict[str, pd.DataFrame]:
    """
    Fetches worksheets using User OAuth2 credentials (Google Sign-In token).
    """
    try:
        import gspread
        from google.oauth2.credentials import Credentials
    except ImportError:
        logger.warning("[Google Sheets Sync] gspread / google-auth not installed.")
        return {}

    access_token = token_data.get("access_token")
    if not access_token:
        return {}

    creds = Credentials(
        token=access_token,
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id") or settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(sheet_id)
    result_sheets = {}
    for ws in spreadsheet.worksheets():
        data = ws.get_all_records()
        if data:
            result_sheets[ws.title] = pd.DataFrame(data)
            
    return result_sheets


# ─────────────────────────────────────────────────────────────────────────────
# 3. Unified Ingestion & Synchronization Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def extract_sheet_id(sheet_id_or_url: Optional[str]) -> Optional[str]:
    """Extract clean Google Sheet ID from URL or bare ID string."""
    if not sheet_id_or_url:
        return None
    val = sheet_id_or_url.strip()
    if "/spreadsheets/d/" in val:
        try:
            parts = val.split("/spreadsheets/d/")[1]
            return parts.split("/")[0].split("?")[0]
        except Exception:
            pass
    return val


def sync_google_sheets(
    sheet_id: Optional[str] = None,
    credentials_file: Optional[str] = None,
    db_path: str = "retail_clothing.db",
    sheet_names: Optional[List[str]] = None,
    mirror_to_live_data: bool = True
) -> Dict[str, Any]:
    """
    Synchronizes Products, Inventory, and Sales data from a Google Sheet into SQLite.
    Execution hierarchy:
    1. Service Account Credentials (credentials.json)
    2. User OAuth2 Token (google_user_token.json)
    3. Direct Link-Shared HTTP CSV Export URL
    """
    raw_sheet_id = sheet_id or settings.GOOGLE_SHEET_ID
    target_sheet_id = extract_sheet_id(raw_sheet_id)
    target_creds = credentials_file or settings.GOOGLE_CREDENTIALS_FILE
    target_sheets = sheet_names or ["Products", "Inventory", "Sales"]

    if not target_sheet_id:
        return {
            "status": "SKIPPED",
            "message": "GOOGLE_SHEET_ID is not configured.",
            "sheets_processed": [],
            "rows_synced": 0,
            "synced_at": datetime.now().isoformat()
        }

    logger.info(f"[Google Sheets Sync] Initiating sync for Sheet ID: {target_sheet_id}")

    extracted_sheets: Dict[str, pd.DataFrame] = {}
    method_used = "UNKNOWN"

    # Method A: Try Service Account Credentials if file exists
    if target_creds and os.path.exists(target_creds):
        try:
            extracted_sheets = fetch_sheet_via_service_account(target_sheet_id, target_creds)
            if extracted_sheets:
                method_used = "SERVICE_ACCOUNT_API"
        except Exception as sa_err:
            logger.warning(f"[Google Sheets Sync] Service account fetch failed: {sa_err}")

    # Method B: Try User OAuth Token if available
    if not extracted_sheets:
        user_tokens = load_user_oauth_token()
        if user_tokens:
            try:
                extracted_sheets = fetch_sheet_via_oauth_token(target_sheet_id, user_tokens)
                if extracted_sheets:
                    method_used = "USER_OAUTH_TOKEN"
            except Exception as oauth_err:
                logger.warning(f"[Google Sheets Sync] OAuth fetch failed: {oauth_err}")

    # Method C: Fallback to Link-Shared HTTP CSV Export
    if not extracted_sheets:
        seen_headers = []
        for s_name in target_sheets:
            try:
                df = fetch_sheet_via_http_csv(target_sheet_id, s_name)
                if not df.empty and len(df.columns) > 1:
                    hdr_key = tuple(list(df.columns)[:5])
                    # If this tab just repeats the default first tab, only save if name matches
                    if hdr_key not in seen_headers or s_name.lower() in ("products", "inventory", "sales"):
                        extracted_sheets[s_name] = df
                        seen_headers.append(hdr_key)
            except Exception as e_http:
                logger.debug(f"[Google Sheets Sync] Sheet '{s_name}' fetch note: {e_http}")
        if extracted_sheets:
            method_used = "HTTP_CSV_EXPORT"

    if not extracted_sheets:
        err_msg = f"Could not fetch worksheets from Google Sheet {target_sheet_id}. Check Sheet ID and permissions."
        logger.error(f"[Google Sheets Sync] {err_msg}")
        return {
            "status": "FAILED",
            "sheet_id": target_sheet_id,
            "error": err_msg,
            "synced_at": datetime.now().isoformat()
        }

    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    total_rows = 0
    sheets_processed = []

    try:
        for sheet_title, df in extracted_sheets.items():
            if df.empty:
                continue

            s_lower = sheet_title.lower().strip()
            sheet_rows = 0

            if "product" in s_lower or "item" in s_lower:
                sheet_rows = _upsert_products(conn, df)
            elif "inventory" in s_lower or "stock" in s_lower:
                sheet_rows = _upsert_inventory(conn, df)
            elif "sale" in s_lower or "order" in s_lower or "voucher" in s_lower:
                sheet_rows = _upsert_sales(conn, df)
            else:
                cols = [str(c).lower() for c in df.columns]
                if any("stock" in c for c in cols):
                    sheet_rows = _upsert_inventory(conn, df)
                elif any("sale" in c or "qty" in c for c in cols):
                    sheet_rows = _upsert_sales(conn, df)
                elif any("sku" in c or "product" in c for c in cols):
                    sheet_rows = _upsert_products(conn, df)

            total_rows += sheet_rows
            sheets_processed.append(sheet_title)

        # Mirror backup to live_data/google_sheets_backup.xlsx
        if mirror_to_live_data and extracted_sheets:
            try:
                project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                meta_dir = os.path.join(project_dir, "live_data")
                os.makedirs(meta_dir, exist_ok=True)
                backup_path = os.path.join(meta_dir, "google_sheets_backup.xlsx")
                with pd.ExcelWriter(backup_path, engine="openpyxl") as writer:
                    for s_name, s_df in extracted_sheets.items():
                        s_df.to_excel(writer, sheet_name=s_name[:30], index=False)
            except Exception as b_err:
                logger.warning(f"[Google Sheets Sync] Backup write note: {b_err}")

        conn.execute(
            "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('GOOGLE_SHEETS', ?, 'SUCCESS', ?)",
            (f"SHEET_{target_sheet_id[:10]}", total_rows)
        )
        conn.commit()

    except Exception as sync_err:
        conn.rollback()
        logger.error(f"[Google Sheets Sync] Ingestion error: {sync_err}")
        conn.execute(
            "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('GOOGLE_SHEETS', ?, 'FAILED', 0, ?)",
            (f"SHEET_{target_sheet_id[:10]}", str(sync_err))
        )
        conn.commit()
        conn.close()
        return {
            "status": "FAILED",
            "sheet_id": target_sheet_id,
            "error": str(sync_err),
            "synced_at": datetime.now().isoformat()
        }

    conn.close()

    if total_rows > 0:
        try:
            generate_insights(db_path)
        except Exception as e_ins:
            logger.warning(f"Auto insights refresh warning after Google Sheets sync: {e_ins}")

    return {
        "status": "SUCCESS",
        "method": method_used,
        "sheet_id": target_sheet_id,
        "sheets_processed": sheets_processed,
        "rows_synced": total_rows,
        "synced_at": datetime.now().isoformat()
    }
