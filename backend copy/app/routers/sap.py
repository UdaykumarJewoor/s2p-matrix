# routers/sap.py — SAP Integration endpoints (NFR-01)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.invoice import Invoice, GRN
from app.config import settings

# ── Dynamic SAP Backend Router ──
if settings.SAP_INTEGRATION_MODE.lower() == "real":
    from app.utils.sap_client import (
        sync_vendor_to_sap, sync_po_to_sap,
        sync_grn_to_sap, sync_invoice_to_sap,
        get_sap_po_status, get_sap_vendor_details,
    )
    def health_check():
        return {"sap_system": "S4H", "environment": "Production/Real (via REST OData)", "status": "Ready"}
else:
    from app.utils.sap_mock import (
        sync_vendor_to_sap, sync_po_to_sap,
        sync_grn_to_sap, sync_invoice_to_sap,
        get_sap_po_status, get_sap_vendor_details,
        health_check
    )

router = APIRouter()

# ── SAP Health Check ──────────────────────────────────────────
@router.get("/health")
def sap_health():
    """Check SAP system connectivity"""
    return health_check()

# ── Sync Vendor to SAP ────────────────────────────────────────
@router.post("/sync/vendor/{vendor_id}")
def push_vendor_to_sap(vendor_id: int, db: Session = Depends(get_db)):
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if vendor.status != "Approved":
        raise HTTPException(status_code=400,
            detail="Only approved vendors can be synced to SAP")

    result = sync_vendor_to_sap({
        "company_name": vendor.company_name,
        "city"        : vendor.city,
        "state"       : vendor.state,
        "gst_number"  : vendor.gst_number,
    })

    # Save SAP vendor code back
    vendor.sap_vendor_code = result["sap_vendor_code"]
    db.commit()

    return {
        "message"       : result["message"],
        "sap_vendor_code": result["sap_vendor_code"],
        "sap_data"      : result["sap_data"],
        "synced_at"     : result["synced_at"]
    }

# ── Sync PO to SAP ────────────────────────────────────────────
@router.post("/sync/po/{po_id}")
def push_po_to_sap(po_id: int, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in ["Approved", "Sent to Vendor"]:
        raise HTTPException(status_code=400,
            detail=f"PO must be Approved before SAP sync. Current: {po.status}")

    # Get vendor SAP code
    vendor = db.query(Vendor).filter(Vendor.id == po.vendor_id).first()
    sap_vendor = vendor.sap_vendor_code if vendor else None

    # Get line items
    items = db.query(POItem).filter(POItem.po_id == po_id).all()
    items_data = [{
        "description": i.description,
        "quantity"   : float(i.quantity),
        "unit"       : i.unit,
        "unit_price" : float(i.unit_price),
    } for i in items]

    result = sync_po_to_sap({
        "po_number"      : po.po_number,
        "po_date"        : str(po.po_date),
        "sap_vendor_code": sap_vendor,
        "items"          : items_data
    })

    # Save SAP PO number back
    po.sap_po_number = result["sap_po_number"]
    po.status        = "Sent to Vendor"
    db.commit()

    return {
        "message"      : result["message"],
        "sap_po_number": result["sap_po_number"],
        "sap_data"     : result["sap_data"],
        "synced_at"    : result["synced_at"]
    }

# ── Sync GRN to SAP ───────────────────────────────────────────
@router.post("/sync/grn/{grn_id}")
def push_grn_to_sap(grn_id: int, db: Session = Depends(get_db)):
    grn = db.query(GRN).filter(GRN.id == grn_id).first()
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")

    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == grn.po_id).first()

    result = sync_grn_to_sap({
        "grn_number"   : grn.grn_number,
        "received_date": str(grn.received_date),
        "sap_po_number": po.sap_po_number if po else ""
    })

    grn.sap_grn_number = result["sap_grn_number"]
    db.commit()

    return {
        "message"       : result["message"],
        "sap_grn_number": result["sap_grn_number"],
        "sap_data"      : result["sap_data"],
        "synced_at"     : result["synced_at"]
    }

# ── Sync Invoice to SAP ───────────────────────────────────────
@router.post("/sync/invoice/{invoice_id}")
def push_invoice_to_sap(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.match_status != "Matched":
        raise HTTPException(status_code=400,
            detail="Invoice must pass 3-way match before SAP sync")

    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == invoice.po_id).first() if invoice.po_id else None

    vendor = db.query(Vendor).filter(
        Vendor.id == invoice.vendor_id).first()

    result = sync_invoice_to_sap({
        "invoice_number" : invoice.invoice_number,
        "invoice_date"   : str(invoice.invoice_date),
        "total_amount"   : float(invoice.total_amount),
        "tax_amount"     : float(invoice.tax_amount or 0),
        "sap_vendor_code": vendor.sap_vendor_code if vendor else "",
        "sap_po_number"  : po.sap_po_number if po else ""
    })

    return {
        "message"           : result["message"],
        "sap_invoice_number": result["sap_invoice_number"],
        "sap_data"          : result["sap_data"],
        "synced_at"         : result["synced_at"]
    }

# ── Read PO Status from SAP ───────────────────────────────────
@router.get("/po-status/{sap_po_number}")
def read_po_from_sap(sap_po_number: str):
    return get_sap_po_status(sap_po_number)

# ── Read Vendor from SAP ──────────────────────────────────────
@router.get("/vendor/{sap_vendor_code}")
def read_vendor_from_sap(sap_vendor_code: str):
    return get_sap_vendor_details(sap_vendor_code)

# ── Full Sync Status Dashboard ────────────────────────────────
@router.get("/sync-status")
def sap_sync_status(db: Session = Depends(get_db)):
    """Shows what's synced to SAP and what's pending"""

    total_vendors    = db.query(Vendor).filter(Vendor.status == "Approved").count()
    synced_vendors   = db.query(Vendor).filter(
                           Vendor.sap_vendor_code.isnot(None)).count()

    total_pos        = db.query(PurchaseOrder).filter(
                           PurchaseOrder.status.in_(
                               ["Approved","Sent to Vendor","Received","Closed"])
                       ).count()
    synced_pos       = db.query(PurchaseOrder).filter(
                           PurchaseOrder.sap_po_number.isnot(None)).count()

    total_grns       = db.query(GRN).count()
    synced_grns      = db.query(GRN).filter(
                           GRN.sap_grn_number.isnot(None)).count()

    return {
        "sap_system" : "SAP S/4HANA MM (Mock Mode)",
        "company_code": "MXCS",
        "sync_status": {
            "vendors" : {
                "total" : total_vendors,
                "synced": synced_vendors,
                "pending": total_vendors - synced_vendors
            },
            "purchase_orders": {
                "total" : total_pos,
                "synced": synced_pos,
                "pending": total_pos - synced_pos
            },
            "grns": {
                "total" : total_grns,
                "synced": synced_grns,
                "pending": total_grns - synced_grns
            }
        },
        "note": "Running in Mock Mode. Replace sap_mock.py with real SAP OData calls for production."
    }