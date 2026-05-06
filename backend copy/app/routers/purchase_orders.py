# routers/purchase_orders.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.quotation import Quotation, QuotationItem
from app.models.vendor import Vendor
from app.models.rfq import RFQ
from app.utils.audit import log_action
from app.services.email_service import send_po_to_vendor
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

router = APIRouter()

class POItemIn(BaseModel):
    item_code   : Optional[str] = None
    description : str
    quantity    : float
    unit        : Optional[str] = "PCS"
    unit_price  : float
    tax_percent : Optional[float] = 18.0

class POCreate(BaseModel):
    vendor_id        : int
    quotation_id     : Optional[int] = None
    rfq_id           : Optional[int] = None
    po_date          : date
    delivery_date    : Optional[date] = None
    payment_terms    : Optional[str] = None
    incoterms        : Optional[str] = "DAP — Gandhinagar"
    department       : Optional[str] = "Procurement"
    delivery_address : Optional[str] = None
    created_by       : Optional[str] = "system"
    notes            : Optional[str] = None
    items            : List[POItemIn] = []

def generate_po_number(db: Session) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(PurchaseOrder.id)).scalar() or 0
    return f"PO-{year}-{str(max_id + 1).zfill(4)}"

# GET all POs
@router.get("/")
def get_pos(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(PurchaseOrder)
    if status:
        query = query.filter(PurchaseOrder.status == status)
    return {"purchase_orders": query.order_by(PurchaseOrder.created_at.desc()).all()}

# GET single PO
@router.get("/{po_id}")
def get_po(po_id: int, db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    from app.models.invoice import GRN, GRNItem
    
    po = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.items)).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")
    
    # Calculate delivery progress per item
    # Get all accepted items across all GRNs for this PO
    accepted_items = db.query(GRNItem.po_item_id, func.sum(GRNItem.accepted_qty).label("total_accepted"))\
        .join(GRN)\
        .filter(GRN.po_id == po_id)\
        .filter(GRN.quality_status != "GRN Payment Run: Failed")\
        .group_by(GRNItem.po_item_id).all()
    
    accepted_map = {item.po_item_id: float(item.total_accepted) for item in accepted_items}
    
    # Enrich PO items with balance data
    items_out = []
    for it in po.items:
        delivered = accepted_map.get(it.id, 0.0)
        remaining = max(0, float(it.quantity) - delivered)
        
        # We convert to dict to add custom fields
        it_dict = {
            "id": it.id,
            "item_code": it.item_code,
            "description": it.description,
            "quantity": float(it.quantity),
            "unit": it.unit,
            "unit_price": float(it.unit_price),
            "tax_percent": float(it.tax_percent),
            "total_price": float(it.total_price),
            "delivered_qty": delivered,
            "remaining_qty": remaining
        }
        items_out.append(it_dict)

    # Prepare response
    res = {
        "id": po.id,
        "po_number": po.po_number,
        "vendor_id": po.vendor_id,
        "status": po.status,
        "total_amount": float(po.total_amount),
        "items": items_out
    }
    return res

# POST create PO
@router.post("/")
def create_po(data: POCreate, db: Session = Depends(get_db)):
    subtotal   = sum(i.quantity * i.unit_price for i in data.items)
    tax_amount = sum(i.quantity * i.unit_price * i.tax_percent / 100 for i in data.items)
    total      = subtotal + tax_amount

    po = PurchaseOrder(
        po_number        = generate_po_number(db),
        vendor_id        = data.vendor_id,
        quotation_id     = data.quotation_id,
        rfq_id           = data.rfq_id,
        po_date          = data.po_date,
        delivery_date    = data.delivery_date,
        subtotal         = subtotal,
        tax_amount       = tax_amount,
        total_amount     = total,
        payment_terms    = data.payment_terms,
        incoterms        = data.incoterms,
        department       = data.department,
        delivery_address = data.delivery_address,
        created_by       = data.created_by,
        notes            = data.notes,
        status           = "Draft"
    )
    db.add(po)
    db.flush()

    for item in data.items:
        db.add(POItem(
            po_id       = po.id,
            item_code   = item.item_code,
            description = item.description,
            quantity    = item.quantity,
            unit        = item.unit,
            unit_price  = item.unit_price,
            tax_percent = item.tax_percent,
            total_price = item.quantity * item.unit_price * (1 + item.tax_percent / 100)
        ))

    db.commit()
    db.refresh(po)

    if data.rfq_id:
        rfq = db.query(RFQ).filter(RFQ.id == data.rfq_id).first()
        if rfq:
            rfq.status = "Closed"
            db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="CREATE",
        changed_by=data.created_by,
        old_values=None,
        new_values={"status": "Draft", "po_number": po.po_number, "total_amount": float(po.total_amount)},
        db=db
    )

    return {"message": "Purchase Order created", "po_number": po.po_number, "po": po}

# POST submit for approval (L1)
@router.post("/{po_id}/submit")
def submit_for_approval(po_id: int, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    old_status = po.status
    po.status = "Pending L1 Approval"
    db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="UPDATE",
        changed_by="system",
        old_values={"status": old_status},
        new_values={"status": po.status},
        db=db
    )

    return {"message": f"PO {po.po_number} submitted for L1 approval"}

# POST L1 approve
@router.post("/{po_id}/approve-l1")
def approve_l1(po_id: int, approver: str, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    old_status = po.status
    po.status        = "Pending L2 Approval"
    po.l1_approver   = approver
    po.l1_approved_at = datetime.utcnow()
    db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="APPROVE",
        changed_by=approver,
        old_values={"status": old_status},
        new_values={"status": po.status, "l1_approver": approver},
        db=db
    )

    return {"message": f"L1 approved by {approver}. Sent for L2 approval."}

# POST L2 approve — final approval
@router.post("/{po_id}/approve-l2")
def approve_l2(po_id: int, approver: str, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    old_status = po.status
    po.status        = "Approved"
    po.l2_approver   = approver
    po.l2_approved_at = datetime.utcnow()
    db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="APPROVE",
        changed_by=approver,
        old_values={"status": old_status},
        new_values={"status": po.status, "l2_approver": approver},
        db=db
    )

    # ── ADVANCE PAYMENT TRIGGER ──
    # If terms say e.g. "30% Advance", auto-generate a Proforma Invoice for Finance
    import re
    from app.models.invoice import Invoice
    
    terms = po.payment_terms or ""
    match = re.search(r"(\d+)%\s*Advance", terms, re.IGNORECASE)
    if match:
        advance_pct = float(match.group(1))
        advance_amt = round(float(po.total_amount) * (advance_pct / 100), 2)
        
        # Create Proforma Invoice
        proforma = Invoice(
            invoice_number = f"PRO-{po.po_number}-ADV",
            internal_ref   = f"ADV-{po.po_number}",
            vendor_id      = po.vendor_id,
            po_id          = po.id,
            invoice_date   = datetime.utcnow().date(),
            subtotal       = round(float(po.subtotal) * (advance_pct / 100), 2),
            tax_amount     = round(float(po.tax_amount) * (advance_pct / 100), 2),
            total_amount   = advance_amt,
            match_status   = "Matched", # Advance is pre-approved by PO approval
            match_notes    = f"SYSTEM-GENERATED PROFORMA: {advance_pct}% Advance as per PO terms.",
            status         = "Approved",
            payment_status = "Unpaid"
        )
        db.add(proforma)
        db.commit()
        print(f"Generated {advance_pct}% Advance Proforma for PO {po.po_number}")

    return {"message": f"PO {po.po_number} fully approved by {approver}. Proforma generated if terms require advance."}

# POST reject PO
@router.post("/{po_id}/reject")
def reject_po(po_id: int, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    old_status = po.status
    po.status = "Cancelled"
    db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="REJECT",
        changed_by="system",
        old_values={"status": old_status},
        new_values={"status": po.status},
        db=db
    )

    return {"message": f"PO {po.po_number} rejected"}


# ── AUTO-GENERATE PO FROM QUOTATION ──────────────────────────────────────────
@router.post("/generate-from-quotation/{quotation_id}")
def generate_po_from_quotation(quotation_id: int, db: Session = Depends(get_db)):
    """
    Automatically generates a Purchase Order from a selected/recommended Quotation.
    Idempotent: if a PO already exists for this quotation, returns it instead of creating a duplicate.
    """
    # ── IDEMPOTENCY CHECK ─────────────────────────────────────────
    existing_po = db.query(PurchaseOrder).filter(
        PurchaseOrder.quotation_id == quotation_id
    ).first()
    if existing_po:
        return {
            "message"  : f"PO {existing_po.po_number} already exists for this quotation",
            "po_id"    : existing_po.id,
            "po_number": existing_po.po_number,
            "existing" : True
        }

    # Load quotation
    quot = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quot:
        raise HTTPException(status_code=404, detail="Quotation not found")

    # Load vendor
    vendor = db.query(Vendor).filter(Vendor.id == quot.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Load quotation items
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation_id).all()

    # Calculate totals from items if quotation totals are 0
    if items:
        subtotal   = sum(float(qi.quantity) * float(qi.unit_price) for qi in items)
        tax_amount = sum(float(qi.quantity) * float(qi.unit_price) * float(qi.tax_percent) / 100 for qi in items)
        total      = subtotal + tax_amount
    else:
        subtotal   = float(quot.subtotal   or 0)
        tax_amount = float(quot.tax_amount or 0)
        total      = float(quot.total_amount or 0)

    # Expected delivery date = today + delivery_days
    delivery_date = None
    if quot.delivery_days:
        from datetime import timedelta
        delivery_date = date.today() + timedelta(days=int(quot.delivery_days))

    po = PurchaseOrder(
        po_number        = generate_po_number(db),
        vendor_id        = quot.vendor_id,
        quotation_id     = quot.id,
        rfq_id           = quot.rfq_id,
        po_date          = date.today(),
        delivery_date    = delivery_date,
        subtotal         = subtotal,
        tax_amount       = tax_amount,
        total_amount     = total,
        payment_terms    = quot.payment_terms,
        delivery_address = "Matrix Comsec Pvt. Ltd., Plot No. 12, Electronic Estate, Gandhinagar - 382 021, Gujarat, India",
        created_by       = "system",
        notes            = f"Auto-generated from Quotation {quot.quotation_number} (AI Recommended)",
        status           = "Draft"
    )
    db.add(po)
    db.flush()

    # Map quotation items → PO items
    from app.models.rfq import RFQItem
    for qi in items:
        # Get the actual unit from the RFQ, fallback to PCS
        rfq_item = db.query(RFQItem).filter(RFQItem.id == qi.rfq_item_id).first()
        actual_unit = rfq_item.unit if rfq_item and getattr(rfq_item, 'unit', None) else 'PCS'

        db.add(POItem(
            po_id       = po.id,
            item_code   = getattr(qi, 'item_code', None) or (rfq_item.item_code if rfq_item else None),
            description = qi.description,
            quantity    = float(qi.quantity),
            unit        = actual_unit,
            unit_price  = float(qi.unit_price),
            tax_percent = float(qi.tax_percent),
            total_price = float(qi.total_price)
        ))

    # Mark quotation as Selected
    quot.status = "Selected"

    # Close the associated RFQ since the procurement process has reached the PO stage
    rfq = db.query(RFQ).filter(RFQ.id == quot.rfq_id).first()
    if rfq:
        rfq.status = "Closed"

    db.commit()

    # Capture po values before refresh to avoid serialization issues
    po_id     = po.id
    po_number = po.po_number

    try:
        log_action(
            table_name="purchase_orders",
            record_id=po_id,
            action="CREATE",
            changed_by="system",
            old_values=None,
            new_values={
                "po_number"    : po_number,
                "quotation_id" : quotation_id,
                "vendor"       : vendor.company_name,
                "total_amount" : total
            },
            db=db
        )
    except Exception:
        pass  # Log failures should never block PO creation

    return {
        "message"  : f"PO {po_number} successfully generated from Quotation {quot.quotation_number}",
        "po_id"    : po_id,
        "po_number": po_number,
        "existing" : False
    }


# ── FULL PO DETAIL FOR PRINTABLE TEMPLATE ────────────────────────────────────
@router.get("/{po_id}/detail")
def get_po_detail(po_id: int, db: Session = Depends(get_db)):
    """Returns full PO data including vendor info and line items for the printable template."""
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    vendor = db.query(Vendor).filter(Vendor.id == po.vendor_id).first()
    items  = db.query(POItem).filter(POItem.po_id == po_id).all()

    # Load RFQ if linked
    rfq = db.query(RFQ).filter(RFQ.id == po.rfq_id).first() if po.rfq_id else None

    return {
        "po": {
            "id"              : po.id,
            "po_number"       : po.po_number,
            "status"          : po.status,
            "po_date"         : str(po.po_date) if po.po_date else None,
            "delivery_date"   : str(po.delivery_date) if po.delivery_date else None,
            "payment_terms"   : po.payment_terms,
            "delivery_address": po.delivery_address,
            "subtotal"        : float(po.subtotal or 0),
            "tax_amount"      : float(po.tax_amount or 0),
            "total_amount"    : float(po.total_amount or 0),
            "notes"           : po.notes,
            "created_by"      : po.created_by,
            "l1_approver"     : po.l1_approver,
            "l2_approver"     : po.l2_approver,
        },
        "vendor": {
            "id"            : vendor.id if vendor else None,
            "company_name"  : vendor.company_name if vendor else "—",
            "vendor_code"   : vendor.vendor_code if vendor else "—",
            "address"       : vendor.address if vendor else "—",
            "gstin"         : getattr(vendor, "gstin", "—"),
            "contact_person": vendor.contact_person if vendor else "—",
            "email"         : vendor.email if vendor else "—",
            "phone"         : vendor.phone if vendor else "—",
            "oem_approved"  : vendor.oem_approved if vendor else False,
        },
        "rfq": {
            "rfq_number": rfq.rfq_number if rfq else None,
            "title"     : rfq.title if rfq else None,
        } if rfq else None,
        "items": [
            {
                "id"         : i.id,
                "item_code"  : i.item_code,
                "description": i.description,
                "quantity"   : float(i.quantity),
                "unit"       : i.unit or "PCS",
                "unit_price" : float(i.unit_price),
                "tax_percent": float(i.tax_percent or 18),
                "total_price": float(i.total_price),
            }
            for i in items
        ]
    }


# ── SEND PO TO VENDOR VIA EMAIL ───────────────────────────────────────────────
@router.post("/{po_id}/send-to-vendor")
def send_po_email_to_vendor(po_id: int, db: Session = Depends(get_db)):
    """
    Sends the approved PO to the vendor via email.
    Updates PO status to 'Sent to Vendor'.
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    vendor = db.query(Vendor).filter(Vendor.id == po.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if not vendor.email:
        raise HTTPException(status_code=400, detail="Vendor has no email address configured")

    items = db.query(POItem).filter(POItem.po_id == po_id).all()

    result = send_po_to_vendor(
        vendor_email     = vendor.email,
        vendor_name      = vendor.company_name,
        contact_person   = vendor.contact_person or vendor.company_name,
        po_id            = po.id,
        po_number        = po.po_number,
        po_date          = str(po.po_date) if po.po_date else "—",
        delivery_date    = str(po.delivery_date) if po.delivery_date else None,
        payment_terms    = po.payment_terms,
        delivery_address = po.delivery_address,
        items            = [
            {
                "description": i.description,
                "quantity"   : float(i.quantity),
                "unit_price" : float(i.unit_price),
                "total_price": float(i.total_price),
            }
            for i in items
        ],
        subtotal    = float(po.subtotal or 0),
        tax_amount  = float(po.tax_amount or 0),
        total_amount= float(po.total_amount or 0),
        notes       = po.notes or ""
    )

    # Update PO status
    old_status = po.status
    po.status = "Sent to Vendor"
    db.commit()

    log_action(
        table_name="purchase_orders",
        record_id=po.id,
        action="SEND",
        changed_by="system",
        old_values={"status": old_status},
        new_values={"status": "Sent to Vendor", "email_to": vendor.email},
        db=db
    )

    return {
        "message"     : f"PO {po.po_number} sent to {vendor.email}",
        "email_status": result.get("status"),
        "to"          : vendor.email,
        "po_number"   : po.po_number
    }