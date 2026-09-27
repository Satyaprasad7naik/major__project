"""
Tally Automated Synchronization Service for InsightOS.
Supports:
1. Auto-watching and ingesting Tally export directory (XML/Excel auto-dumps)
2. HTTP XML server pull from Tally ERP 9 / TallyPrime (Port 9000)
3. Direct sync into SQLite and triggering Auto Insights.
"""

import os
import glob
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import pandas as pd

from app.core.config import settings
from app.core.logger import logger
from app.services.auto_insights import generate_insights, get_db_connection
from app.services.excel_sync import (
    init_sync_schema,
    get_sync_metadata,
    save_sync_metadata,
    sync_excel_to_db,
    _upsert_products,
    _upsert_inventory,
    _upsert_sales
)
from app.services.tally_sync import (
    ping_tally_server,
    auto_sync_tally,
    parse_tally_xml,
    export_tally_to_excel_files,
    sync_tally_xml_to_db
)


def get_tally_folder_metadata(metadata_path: str) -> Dict[str, float]:
    """Load cached file modification timestamps for Tally export folder."""
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read Tally sync metadata: {e}")
    return {}


def save_tally_folder_metadata(metadata_path: str, data: Dict[str, float]):
    """Save updated file modification timestamps for Tally export folder."""
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save Tally sync metadata: {e}")


def sync_tally_export_folder(
    export_folder: str,
    db_path: str = "retail_clothing.db",
    live_data_dir: str = "live_data",
    force: bool = False
) -> Dict[str, Any]:
    """
    Scans a local/shared folder where Tally automatically dumps exported XML or Excel files.
    Processes any new or updated files, extracts stock and sales data, updates live_data/ and DB.
    """
    if not os.path.exists(export_folder):
        return {
            "status": "SKIPPED",
            "message": f"Tally export folder '{export_folder}' does not exist.",
            "files_processed": [],
            "rows_synced": 0
        }

    metadata_path = os.path.join(export_folder, ".tally_export_metadata.json")
    meta = get_tally_folder_metadata(metadata_path)

    all_files = [
        f for f in os.listdir(export_folder)
        if (f.endswith(".xml") or f.endswith(".xlsx") or f.endswith(".xls")) and not f.startswith("~$")
    ]

    if not all_files:
        return {
            "status": "SKIPPED",
            "message": f"No Tally export files (.xml, .xlsx) found in '{export_folder}'.",
            "files_processed": [],
            "rows_synced": 0
        }

    files_processed = []
    total_rows = 0
    errors = []

    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    for file_name in all_files:
        file_path = os.path.join(export_folder, file_name)
        try:
            mtime = os.path.getmtime(file_path)
            last_mtime = meta.get(file_name, 0.0)

            if not force and mtime <= last_mtime:
                continue

            logger.info(f"[Tally Folder Sync] Ingesting updated Tally file: {file_name}")

            if file_name.endswith(".xml"):
                with open(file_path, "r", encoding="utf-8", errors="replace") as xf:
                    xml_content = xf.read()
                parsed = parse_tally_xml(xml_content)
                export_tally_to_excel_files(parsed, live_data_dir=live_data_dir)
                sync_res = sync_tally_xml_to_db(xml_content, db_path=db_path)
                file_rows = sync_res.get("rows_synced", 0)
            else:
                # Excel file exported by Tally
                excel_data = pd.read_excel(file_path, sheet_name=None)
                file_rows = 0
                for sheet_name, df in excel_data.items():
                    if df.empty:
                        continue
                    sheet_lower = sheet_name.lower().strip()
                    if "stock" in sheet_lower or "inventory" in sheet_lower:
                        file_rows += _upsert_inventory(conn, df)
                    elif "sale" in sheet_lower or "voucher" in sheet_lower:
                        file_rows += _upsert_sales(conn, df)
                    elif "item" in sheet_lower or "product" in sheet_lower:
                        file_rows += _upsert_products(conn, df)
                    else:
                        cols = [c.lower() for c in df.columns]
                        if any("stock" in c for c in cols):
                            file_rows += _upsert_inventory(conn, df)
                        elif any("sale" in c or "qty" in c for c in cols):
                            file_rows += _upsert_sales(conn, df)

            meta[file_name] = mtime
            total_rows += file_rows
            files_processed.append(file_name)

            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('TALLY_FOLDER', ?, 'SUCCESS', ?)",
                (file_name, file_rows)
            )
            conn.commit()

        except Exception as exc:
            err_msg = f"Failed to sync Tally file {file_name}: {exc}"
            logger.error(f"[Tally Folder Sync] {err_msg}")
            errors.append(err_msg)
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('TALLY_FOLDER', ?, 'FAILED', 0, ?)",
                (file_name, str(exc))
            )
            conn.commit()

    save_tally_folder_metadata(metadata_path, meta)
    conn.close()

    if files_processed:
        try:
            generate_insights(db_path)
        except Exception as e_ins:
            logger.warning(f"Auto insights refresh warning after Tally folder sync: {e_ins}")

    return {
        "status": "SUCCESS" if files_processed else ("SKIPPED" if not errors else "FAILED"),
        "method": "EXPORT_FOLDER",
        "export_folder": export_folder,
        "files_processed": files_processed,
        "rows_synced": total_rows,
        "errors": errors,
        "synced_at": datetime.now().isoformat()
    }


def run_tally_auto_sync(
    host: Optional[str] = None,
    port: Optional[int] = None,
    company: Optional[str] = None,
    export_folder: Optional[str] = None,
    live_data_dir: str = "live_data",
    db_path: str = "retail_clothing.db",
    force: bool = False
) -> Dict[str, Any]:
    """
    Orchestrates automated Tally synchronization:
    1. First checks if a configured export folder has fresh files.
    2. If not, queries Tally's native HTTP XML Server (Port 9000).
    3. Seamlessly updates live_data/ and SQLite DB, triggering fresh insights.
    """
    target_folder = export_folder or settings.TALLY_EXPORT_FOLDER
    target_host = host or settings.TALLY_HOST
    target_port = port or settings.TALLY_PORT
    target_company = company or settings.TALLY_COMPANY

    logger.info(f"[Tally Auto Sync] Initiating automated Tally sync (Folder: {target_folder}, HTTP: {target_host}:{target_port})...")

    # Step 1: Check Export Folder if defined and exists
    if target_folder and os.path.exists(target_folder):
        folder_result = sync_tally_export_folder(
            export_folder=target_folder,
            db_path=db_path,
            live_data_dir=live_data_dir,
            force=force
        )
        if folder_result.get("files_processed"):
            return folder_result

    # Step 2: Fallback to HTTP XML Server Pull
    http_result = auto_sync_tally(
        host=target_host,
        port=target_port,
        company=target_company,
        live_data_dir=live_data_dir,
        db_path=db_path
    )

    return http_result
