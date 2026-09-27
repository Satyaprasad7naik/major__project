"""
Invoice Ingestion & Reconciliation API Endpoints for InsightOS.
Endpoints specified in AUTO_INSIGHTS_FEATURE.md:
- POST /api/v1/invoices/parse
- POST /api/v1/invoices/confirm
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.modules.invoice_parser import InvoiceParserService, ParsedInvoice
from app.services.auto_insights import get_db_connection
from app.core.logger import logger

router = APIRouter(prefix="/invoices", tags=["invoices"])


class IntakeConfirmationItem(BaseModel):
    sku_id: str
    quantity: int


class IntakeConfirmationRequest(BaseModel):
    invoice_number: str
    items: List[IntakeConfirmationItem]
    db_path: Optional[str] = Field("retail_clothing.db", description="Database file path")


@router.post("/parse", response_model=dict)
async def parse_invoice(
    file: UploadFile = File(...),
    db_path: Optional[str] = Form("retail_clothing.db")
):
    """
    Accepts PDF or Image (PNG/JPEG) invoice uploads, executes structured multimodal
    extraction, and runs catalog reconciliation via entity resolution.
    """
    filename = file.filename or "invoice.pdf"
    mime_type = file.content_type or "application/octet-stream"
    
    # Check mime type or extension
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/jpg", "text/plain"]
    if mime_type not in allowed_types and not any(filename.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".jpeg", ".txt"]):
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{mime_type}'. Must be PDF, PNG, or JPEG.")
        
    try:
        contents = await file.read()
        parsed: ParsedInvoice = InvoiceParserService.parse_invoice_stream(
            filename=filename,
            content_bytes=contents,
            mime_type=mime_type,
            db_path=db_path or "retail_clothing.db"
        )
        return {
            "status": "SUCCESS",
            "message": f"Invoice {parsed.invoice_number} parsed successfully with {len(parsed.line_items)} line items matched.",
            "extracted_data": parsed.dict()
        }
    except Exception as exc:
        logger.error(f"Invoice parsing failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/confirm", response_model=dict)
async def confirm_invoice_intake(payload: IntakeConfirmationRequest = Body(...)):
    """
    Reconciliation & Ingestion Gate:
    Validates verified line items and stage-updates stock balances in the inventory table.
    """
    clean_db = payload.db_path or "retail_clothing.db"
    conn = None
    try:
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()
        
        updated_items = []
        for itm in payload.items:
            # Update inventory count
            cursor.execute("""
                UPDATE inventory
                SET stock_count = stock_count + ?, last_restocked_at = CURRENT_TIMESTAMP
                WHERE sku = ?
            """, (itm.quantity, itm.sku_id))
            
            # Fetch updated count
            row = cursor.execute("SELECT stock_count FROM inventory WHERE sku = ?", (itm.sku_id,)).fetchone()
            new_stock = row["stock_count"] if row else None
            
            updated_items.append({
                "sku_id": itm.sku_id,
                "quantity_added": itm.quantity,
                "new_stock_count": new_stock
            })
            
        conn.commit()
        logger.info(f"[InvoiceIntake] Confirmed invoice {payload.invoice_number} with {len(updated_items)} items ingested.")
        
        return {
            "status": "SUCCESS",
            "invoice_number": payload.invoice_number,
            "message": f"Successfully ingested {len(updated_items)} line items into inventory.",
            "updated_items": updated_items
        }
    except Exception as exc:
        logger.error(f"Invoice intake confirmation failed: {exc}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()
