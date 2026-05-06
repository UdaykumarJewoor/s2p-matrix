# routers/rfq.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.vendor import Vendor
from app.models.quotation import Quotation, QuotationItem
from app.utils.audit import log_action
from app.services.email_service import (
    generate_vendor_token, get_token_expiry, send_rfq_invitation
)
from app.services.ai_discovery import discover_vendors_for_category
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

router = APIRouter()

# ── Pydantic Schemas ──────────────────────────────────────────
class RFQItemIn(BaseModel):
    item_code     : Optional[str] = None
    description   : str
    quantity      : float
    unit          : Optional[str] = "PCS"
    specification : Optional[str] = None

class RFQCreate(BaseModel):
    title           : str
    description     : Optional[str] = None
    category_id     : Optional[int] = None
    issue_date      : date
    deadline        : date
    estimated_value : Optional[float] = None
    created_by      : Optional[str] = "system"
    items           : List[RFQItemIn] = []
    vendor_ids      : List[int] = []
    target_category : Optional[str] = None

class VendorQuoteItem(BaseModel):
    rfq_item_id  : int
    description  : str
    quantity     : float
    unit_price   : float
    tax_percent  : Optional[float] = 18.0

class VendorQuoteSubmit(BaseModel):
    delivery_days   : int
    payment_terms   : str
    warranty_months : Optional[int] = 12
    notes           : Optional[str] = None
    items           : List[VendorQuoteItem]

# ── Helper ────────────────────────────────────────────────────
def generate_rfq_number(db: Session) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(RFQ.id)).scalar() or 0
    return f"RFQ-{year}-{str(max_id + 1).zfill(4)}"

def generate_quo_number(db: Session) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(Quotation.id)).scalar() or 0
    return f"QUO-{year}-{str(max_id + 1).zfill(4)}"

# ── ROUTES ────────────────────────────────────────────────────

@router.get("/")
def get_rfqs(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(RFQ)
    if status:
        query = query.filter(RFQ.status == status)
    rfqs = query.order_by(RFQ.created_at.desc()).all()
    return {"total": len(rfqs), "rfqs": rfqs}

@router.get("/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    """
    Get single RFQ with list of assigned vendors (including names/emails and AI insights)
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
        
    from app.services.ai_discovery import qualify_vendor, get_recommendation

    vendors_assigned = []
    for rv in rfq.vendors:
        vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()
        
        # Real-time AI Intelligence insights
        ai_score, reasons, flags = qualify_vendor(vendor, db) if vendor else (0, [], [])
        
        # Get history count for transparency (live from POs)
        from app.models.purchase_order import PurchaseOrder
        history_count = db.query(PurchaseOrder).filter(PurchaseOrder.vendor_id == rv.vendor_id).count() if vendor else 0
        
        vendors_assigned.append({
            "vendor_id": rv.vendor_id,
            "vendor_name": vendor.company_name if vendor else f"Vendor #{rv.vendor_id}",
            "email": vendor.email if vendor else "N/A",
            "sent_at": str(rv.sent_at) if rv.sent_at else None,
            "email_status": rv.email_status or "Not Sent",
            "response_status": rv.response_status or "Pending",
            "ai_score": ai_score,
            "ai_reasons": reasons,
            "ai_flags": flags,
            "history_count": history_count,
            "recommendation": get_recommendation(ai_score, flags) if vendor else "N/A"
        })
        
    result = {c.name: getattr(rfq, c.name) for c in rfq.__table__.columns}
    result["vendors"] = vendors_assigned
    result["items"] = [
        {
            "id": i.id,
            "description": i.description,
            "quantity": i.quantity,
            "unit": i.unit
        } for i in rfq.items
    ]
    return result

@router.post("/")
def create_rfq(data: RFQCreate, db: Session = Depends(get_db)):
    rfq = RFQ(
        rfq_number      = generate_rfq_number(db),
        title           = data.title,
        description     = data.description,
        category_id     = data.category_id,
        issue_date      = data.issue_date,
        deadline        = data.deadline,
        estimated_value = data.estimated_value,
        created_by      = data.created_by,
        target_category = data.target_category,
        status          = "Draft"
    )
    db.add(rfq)
    db.flush()

    for item in data.items:
        db.add(RFQItem(
            rfq_id        = rfq.id,
            item_code     = item.item_code,
            description   = item.description,
            quantity      = item.quantity,
            unit          = item.unit,
            specification = item.specification
        ))

    vendors_to_assign = set(data.vendor_ids)
    if data.target_category:
        ai_results = discover_vendors_for_category(data.target_category, db)
        for ai_vendor in ai_results[:10]:
            vendors_to_assign.add(ai_vendor["vendor_id"])

    for vendor_id in vendors_to_assign:
        db.add(RFQVendor(rfq_id=rfq.id, vendor_id=vendor_id))

    db.commit()
    db.refresh(rfq)

    log_action("rfq", rfq.id, "CREATE", data.created_by, None, {"status": "Draft", "rfq_number": rfq.rfq_number}, db)
    return {"message": "RFQ created", "rfq_number": rfq.rfq_number, "rfq": rfq}

@router.post("/{rfq_id}/send")
def send_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    items = [{"description": i.description, "quantity": float(i.quantity), "unit": i.unit} for i in rfq.items]
    results  = []
    sent_count = 0

    for rv in rfq.vendors:
        vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()
        if not vendor: continue

        if not rv.invite_token:
            rv.invite_token  = generate_vendor_token()
            rv.token_expires = get_token_expiry(rfq.deadline)
            rv.token_used    = False

        rv.sent_at = datetime.utcnow()
        email_result = send_rfq_invitation(
            vendor_email=vendor.email, vendor_name=vendor.company_name,
            contact_person=vendor.contact_person or vendor.company_name,
            rfq_number=rfq.rfq_number, rfq_title=rfq.title,
            deadline=str(rfq.deadline), items=items, token=rv.invite_token
        )
        rv.email_status = "Simulated" if email_result["status"] == "simulated" else "Sent"
        results.append({
            "vendor_id": vendor.id, "vendor_name": vendor.company_name,
            "email": vendor.email, "portal_link": email_result["portal_link"],
            "email_status": rv.email_status
        })
        sent_count += 1

    rfq.status = "Sent"
    db.commit()
    return {"message": f"RFQ sent to {sent_count} vendors", "vendors": results}

@router.get("/vendor-portal/{token}")
def get_vendor_portal_data(token: str, db: Session = Depends(get_db)):
    rv = db.query(RFQVendor).filter(RFQVendor.invite_token == token).first()
    if not rv: raise HTTPException(status_code=404, detail="Invalid token")
    
    rfq = db.query(RFQ).filter(RFQ.id == rv.rfq_id).first()
    vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()
    
    return {
        "rfq": {
            "id": rfq.id, "rfq_number": rfq.rfq_number, "title": rfq.title,
            "deadline": str(rfq.deadline),
            "items": [{"id": i.id, "description": i.description, "quantity": float(i.quantity), "unit": i.unit} for i in rfq.items]
        },
        "vendor": {"id": vendor.id, "company_name": vendor.company_name}
    }

@router.post("/vendor-portal/{token}/submit")
def submit_vendor_quotation(token: str, data: VendorQuoteSubmit, db: Session = Depends(get_db)):
    rv = db.query(RFQVendor).filter(RFQVendor.invite_token == token).first()
    if not rv:
        raise HTTPException(status_code=404, detail="Invalid token")

    rfq    = db.query(RFQ).filter(RFQ.id == rv.rfq_id).first()
    vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()

    # --- Correct per-item tax calculation ---
    subtotal   = sum(item.quantity * item.unit_price for item in data.items)
    tax_amount = sum(
        item.quantity * item.unit_price * (item.tax_percent / 100)
        for item in data.items
    )
    total = round(subtotal + tax_amount, 2)

    q_num = generate_quo_number(db)

    quotation = Quotation(
        quotation_number = q_num,
        rfq_id           = rfq.id,
        vendor_id        = vendor.id,
        subtotal         = round(subtotal, 2),
        tax_amount       = round(tax_amount, 2),
        total_amount     = total,
        # --- All vendor-entered fields correctly saved ---
        delivery_days    = data.delivery_days,
        warranty_months  = data.warranty_months if data.warranty_months is not None else 12,
        payment_terms    = data.payment_terms,
        notes            = data.notes,
        status           = "Received"
    )
    db.add(quotation)
    db.flush()

    for item in data.items:
        line_tax   = item.quantity * item.unit_price * (item.tax_percent / 100)
        line_total = item.quantity * item.unit_price + line_tax
        db.add(QuotationItem(
            quotation_id = quotation.id,
            rfq_item_id  = item.rfq_item_id,
            description  = item.description,
            quantity     = item.quantity,
            unit_price   = item.unit_price,
            tax_percent  = item.tax_percent,
            total_price  = round(line_total, 2)
        ))

    rv.response_status = "Responded"
    db.commit()
    return {
        "message"          : "Quotation submitted successfully",
        "quotation_number" : q_num,
        "delivery_days"    : data.delivery_days,
        "warranty_months"  : data.warranty_months,
        "payment_terms"    : data.payment_terms,
        "total_amount"     : total
    }

@router.patch("/{rfq_id}/status")
def update_rfq_status(rfq_id: int, status: str, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq: raise HTTPException(status_code=404, detail="RFQ not found")
    rfq.status = status
    db.commit()
    return {"message": "Updated"}