# routers/quotations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.quotation import Quotation, QuotationItem
from app.models.rfq import RFQVendor
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

router = APIRouter()

class QuotationItemIn(BaseModel):
    rfq_item_id : Optional[int] = None
    description : str
    quantity    : float
    unit_price  : float
    tax_percent : Optional[float] = 18.0

class QuotationCreate(BaseModel):
    rfq_id        : int
    vendor_id     : int
    valid_until   : Optional[date] = None
    payment_terms : Optional[str] = None
    delivery_days : Optional[int] = None
    warranty_months: Optional[int] = 0
    notes         : Optional[str] = None
    items         : List[QuotationItemIn] = []

def generate_quotation_number(db: Session) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(Quotation.id)).scalar() or 0
    return f"QUO-{year}-{str(max_id + 1).zfill(4)}"

# GET all quotations (optionally filter by RFQ)
@router.get("/")
def get_quotations(rfq_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Quotation)
    if rfq_id:
        query = query.filter(Quotation.rfq_id == rfq_id)
    return {"quotations": query.order_by(Quotation.submitted_at.desc()).all()}

# GET single quotation
@router.get("/{quotation_id}")
def get_quotation(quotation_id: int, db: Session = Depends(get_db)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return q

# POST submit quotation
@router.post("/")
def create_quotation(data: QuotationCreate, db: Session = Depends(get_db)):
    # Calculate totals
    subtotal = sum(
        item.quantity * item.unit_price for item in data.items
    )
    tax_amount = sum(
        (item.quantity * item.unit_price * item.tax_percent / 100)
        for item in data.items
    )
    total = subtotal + tax_amount

    quotation = Quotation(
        quotation_number = generate_quotation_number(db),
        rfq_id           = data.rfq_id,
        vendor_id        = data.vendor_id,
        valid_until      = data.valid_until,
        payment_terms    = data.payment_terms,
        delivery_days    = data.delivery_days,
        warranty_months  = data.warranty_months,
        notes            = data.notes,
        subtotal         = subtotal,
        tax_amount       = tax_amount,
        total_amount     = total,
        status           = "Received"
    )
    db.add(quotation)
    db.flush()

    for item in data.items:
        db.add(QuotationItem(
            quotation_id = quotation.id,
            rfq_item_id  = item.rfq_item_id,
            description  = item.description,
            quantity     = item.quantity,
            unit_price   = item.unit_price,
            tax_percent  = item.tax_percent,
            total_price  = item.quantity * item.unit_price * (1 + item.tax_percent / 100)
        ))

    # Update vendor response status on RFQ
    rv = db.query(RFQVendor).filter(
        RFQVendor.rfq_id == data.rfq_id,
        RFQVendor.vendor_id == data.vendor_id
    ).first()
    if rv:
        rv.response_status = "Responded"

    db.commit()
    db.refresh(quotation)
    return {"message": "Quotation submitted", "quotation": quotation}

# GET comparison — all quotes for one RFQ, uses unified AI engine (same as pipeline)
@router.get("/compare/{rfq_id}")
def compare_quotations(
    rfq_id  : int,
    strategy: str = "best_value",    # best_value | lowest_cost
    db: Session = Depends(get_db)
):
    """
    AI Quotation Comparison — delegates to the same quotation_comparator.py
    used by the /api/workflow/run pipeline. Guarantees UI and pipeline agree
    on the winner. Supports ?strategy=best_value or ?strategy=lowest_cost.
    """
    from app.services.quotation_comparator import compare_and_select

    quotes = db.query(Quotation).filter(Quotation.rfq_id == rfq_id).all()
    if not quotes:
        raise HTTPException(status_code=404, detail="No quotations found for this RFQ")

    result = compare_and_select(rfq_id=rfq_id, db=db, strategy=strategy)

    # Build a flat 'comparison' list matching the shape the frontend expects
    comparison = []
    for r in result.get("ranked", []):
        comparison.append({
            "quotation_id"     : r["quotation_id"],
            "quotation_number" : r["quotation_number"],
            "vendor_id"        : r["vendor_id"],
            "vendor_name"      : r["vendor_name"],
            "vendor_type"      : r["vendor_type"],
            "oem_approved"     : r["oem_approved"],
            "total_amount"     : r["total_amount"],
            "delivery_days"    : r["delivery_days"],
            "warranty_months"  : r["warranty_months"],
            "payment_terms"    : r["payment_terms"],
            # Unified scores (all on 0-100 scale, weighted)
            "price_score"      : r["price_score"],
            "delivery_score"   : r["delivery_score"],
            "warranty_score"   : r["warranty_score"],
            "performance_score": r["performance_score"],
            "total_score"      : r["ai_score"],       # alias for frontend compat
            "ai_score"         : r["ai_score"],
            "reasoning"        : r["reasoning"],
            "recommended"      : r["recommended"],
        })

    return {
        "rfq_id"             : rfq_id,
        "strategy"           : strategy,
        "weights"            : result.get("weights_used"),
        "total_quotes"       : result.get("total_quotes"),
        "savings_vs_highest" : result.get("savings_vs_highest"),
        "price_range"        : result.get("price_range"),
        "winner"             : result.get("winner"),
        "comparison"         : comparison,
    }