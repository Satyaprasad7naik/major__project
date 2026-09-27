"""
Shared Network Folder Sync Service for InsightOS.
Monitors a shared network folder (UNC path like \\\\server\\share\\data or mapped network drive)
for updated Excel files (.xlsx, .xls) and synchronizes them into the InsightOS database.
"""

import os
import json
import sqlite3
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


def get_network_sync_metadata(metadata_file: str) -> Dict[str, float]:
    """Load cached file modification timestamps for network folder."""
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read network sync metadata: {e}")
    return {}


def save_network_sync_metadata(metadata_file: str, data: Dict[str, float]):
    """Save updated file modification timestamps for network folder."""
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save network sync metadata: {e}")


def sync_network_folder(
    network_folder_path: Optional[str] = None,
    db_path: str = "retail_clothing.db",
    force: bool = False,
    mirror_to_live_data: bool = True
) -> Dict[str, Any]:
    """
    Scans a shared network folder / UNC path for updated Excel files (.xlsx, .xls)
    and synchronizes them into the InsightOS SQLite database.
    Handles network path unavailability and file locks gracefully.
    """
    folder_path = network_folder_path or settings.NETWORK_FOLDER_PATH

    if not folder_path:
        return {
            "status": "SKIPPED",
            "message": "NETWORK_FOLDER_PATH is not configured.",
            "files_processed": [],
            "rows_synced": 0,
            "synced_at": datetime.now().isoformat()
        }

    # Normalize path (support Windows UNC \\server\share and standard paths)
    normalized_path = os.path.normpath(folder_path)

    # Check network path existence / reachability
    try:
        if not os.path.exists(normalized_path):
            logger.warning(f"[Network Sync] Shared network folder '{normalized_path}' is currently unreachable.")
            return {
                "status": "OFFLINE",
                "message": f"Network folder '{normalized_path}' is unreachable or does not exist.",
                "folder_path": normalized_path,
                "files_processed": [],
                "rows_synced": 0,
                "synced_at": datetime.now().isoformat()
            }
    except Exception as path_err:
        logger.warning(f"[Network Sync] Network folder connection check error: {path_err}")
        return {
            "status": "OFFLINE",
            "message": f"Network folder access error: {str(path_err)}",
            "folder_path": normalized_path,
            "files_processed": [],
            "rows_synced": 0,
            "synced_at": datetime.now().isoformat()
        }

    # Local metadata file to track timestamps even if network path is read-only
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    meta_dir = os.path.join(project_dir, "live_data")
    os.makedirs(meta_dir, exist_ok=True)
    metadata_file = os.path.join(meta_dir, ".network_sync_metadata.json")
    meta = get_network_sync_metadata(metadata_file)

    conn = get_db_connection(db_path)
    init_sync_schema(conn)

    files_processed = []
    total_rows = 0
    errors = []

    try:
        excel_files = [
            f for f in os.listdir(normalized_path)
            if (f.endswith(".xlsx") or f.endswith(".xls")) and not f.startswith("~$")
        ]
    except Exception as list_err:
        conn.close()
        logger.error(f"[Network Sync] Failed to list files in network folder '{normalized_path}': {list_err}")
        return {
            "status": "FAILED",
            "message": f"Failed to list directory contents: {str(list_err)}",
            "folder_path": normalized_path,
            "errors": [str(list_err)],
            "synced_at": datetime.now().isoformat()
        }

    if not excel_files:
        conn.close()
        return {
            "status": "SKIPPED",
            "message": f"No Excel files found in network folder '{normalized_path}'",
            "folder_path": normalized_path,
            "files_processed": [],
            "rows_synced": 0,
            "synced_at": datetime.now().isoformat()
        }

    for file_name in excel_files:
        file_path = os.path.join(normalized_path, file_name)
        try:
            mtime = os.path.getmtime(file_path)
            last_mtime = meta.get(file_name, 0.0)

            if not force and mtime <= last_mtime:
                continue

            logger.info(f"[Network Sync] Ingesting updated network file: {file_name}")

            excel_data = pd.read_excel(file_path, sheet_name=None)
            file_rows = 0

            for sheet_name, df in excel_data.items():
                if df.empty:
                    continue

                sheet_lower = sheet_name.lower().strip()
                if "product" in sheet_lower:
                    file_rows += _upsert_products(conn, df)
                elif "inventory" in sheet_lower or "stock" in sheet_lower:
                    file_rows += _upsert_inventory(conn, df)
                elif "sale" in sheet_lower or "order" in sheet_lower:
                    file_rows += _upsert_sales(conn, df)
                else:
                    cols = [c.lower() for c in df.columns]
                    if any("stock" in c for c in cols):
                        file_rows += _upsert_inventory(conn, df)
                    elif any("sale" in c or "qty" in c for c in cols):
                        file_rows += _upsert_sales(conn, df)
                    elif any("name" in c or "sku" in c for c in cols):
                        file_rows += _upsert_products(conn, df)

            meta[file_name] = mtime
            total_rows += file_rows
            files_processed.append(file_name)

            # Mirror to local live_data/ for local caching
            if mirror_to_live_data:
                try:
                    local_copy_path = os.path.join(meta_dir, file_name)
                    with pd.ExcelWriter(local_copy_path, engine="openpyxl") as writer:
                        for s_name, s_df in excel_data.items():
                            s_df.to_excel(writer, sheet_name=s_name, index=False)
                except Exception as mirror_err:
                    logger.warning(f"[Network Sync] Local mirror write warning for {file_name}: {mirror_err}")

            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced) VALUES ('NETWORK_FOLDER', ?, 'SUCCESS', ?)",
                (file_name, file_rows)
            )
            conn.commit()

        except PermissionError:
            err_msg = f"Network file {file_name} is locked by another user. Skipping."
            logger.warning(f"[Network Sync] {err_msg}")
            errors.append(err_msg)
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('NETWORK_FOLDER', ?, 'SKIPPED', 0, ?)",
                (file_name, err_msg)
            )
            conn.commit()
        except Exception as exc:
            err_msg = f"Failed to sync network file {file_name}: {exc}"
            logger.error(f"[Network Sync] {err_msg}")
            errors.append(err_msg)
            conn.execute(
                "INSERT INTO sync_logs (source_type, file_name, status, rows_synced, error_message) VALUES ('NETWORK_FOLDER', ?, 'FAILED', 0, ?)",
                (file_name, str(exc))
            )
            conn.commit()

    save_network_sync_metadata(metadata_file, meta)
    conn.close()

    status_str = "SUCCESS" if files_processed else ("SKIPPED" if not errors else "FAILED")

    if files_processed:
        try:
            generate_insights(db_path)
        except Exception as e_ins:
            logger.warning(f"Auto insights refresh warning after network folder sync: {e_ins}")

    return {
        "status": status_str,
        "folder_path": normalized_path,
        "files_processed": files_processed,
        "rows_synced": total_rows,
        "errors": errors,
        "synced_at": datetime.now().isoformat()
    }
