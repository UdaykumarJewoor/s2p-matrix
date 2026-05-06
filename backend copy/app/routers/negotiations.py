# routers/negotiations.py — BR-S2P-06 Negotiation Tracking (Item-wise)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, DECIMAL, Enum, ForeignKey, Boolean
from app.database import get_db, Base
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.quotation import Quotation, QuotationItem
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter()

# ── Models ─────────────────────────────────────────────────────────────────────

class Negotiation(Base):
    __tablename__ = "negotiations"
    id                  = Column(Integer, primary_key=True, index=True)
    negotiation_ref     = Column(String(30), unique=True)
    vendor_id           = Column(Integer, ForeignKey("vendors.id"))
    rfq_id              = Column(Integer, nullable=True)
    quotation_id        = Column(Integer, ForeignKey("quotations.id"), nullable=True)
    po_id               = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True)
    subject             = Column(String(255), nullable=False)
    initial_price       = Column(DECIMAL(15,2))
    target_price        = Column(DECIMAL(15,2))
    agreed_price        = Column(DECIMAL(15,2))
    savings_achieved    = Column(DECIMAL(15,2), default=0)
    savings_percent     = Column(DECIMAL(5,2),  default=0)
    payment_terms       = Column(String(100))
    delivery_commitment = Column(String(100))
    warranty_terms      = Column(String(100))
    status              = Column(Enum("Open","In Progress","Agreed","Closed","Failed"), default="Open")
    outcome_notes       = Column(Text)
    negotiated_by       = Column(String(100))
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NegotiationItem(Base):
    """Item-wise negotiation price tracking"""
    __tablename__ = "negotiation_items"
    id                  = Column(Integer, primary_key=True, index=True)
    negotiation_id      = Column(Integer, ForeignKey("negotiations.id", ondelete="CASCADE"))
    quotation_item_id   = Column(Integer, ForeignKey("quotation_items.id"), nullable=True)
    description         = Column(String(500), nullable=False)
    quantity            = Column(DECIMAL(10,2), nullable=False)
    unit                = Column(String(20), default="PCS")
    initial_unit_price  = Column(DECIMAL(15,2), nullable=False)   # original from quotation
    target_unit_price   = Column(DECIMAL(15,2), nullable=True)    # buyer's target
    agreed_unit_price   = Column(DECIMAL(15,2), nullable=True)    # final agreed price
    tax_percent         = Column(DECIMAL(5,2), default=18.00)


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class NegotiationItemIn(BaseModel):
    description         : str
    quantity            : float
    unit                : Optional[str] = "PCS"
    initial_unit_price  : float
    target_unit_price   : Optional[float] = None
    tax_percent         : Optional[float] = 18.0
    quotation_item_id   : Optional[int]  = None

class NegotiationCreate(BaseModel):
    vendor_id           : int
    rfq_id              : Optional[int] = None
    quotation_id        : Optional[int] = None
    po_id               : Optional[int] = None
    subject             : str
    initial_price       : float
    target_price        : float
    payment_terms       : Optional[str] = None
    delivery_commitment : Optional[str] = None
    warranty_terms      : Optional[str] = None
    negotiated_by       : Optional[str] = "Procurement Team"
    items               : Optional[List[NegotiationItemIn]] = []

class NegotiationItemClose(BaseModel):
    negotiation_item_id : int
    agreed_unit_price   : float

class NegotiationUpdate(BaseModel):
    agreed_price        : Optional[float] = None
    payment_terms       : Optional[str]   = None
    delivery_commitment : Optional[str]   = None
    warranty_terms      : Optional[str]   = None
    status              : Optional[str]   = None
    outcome_notes       : Optional[str]   = None
    # Item-wise agreed prices for PO sync
    items               : Optional[List[NegotiationItemClose]] = []


# ── Helpers ────────────────────────────────────────────────────────────────────

def gen_neg_ref(db: Session) -> str:
    from sqlalchemy import func
    max_id = db.query(func.max(Negotiation.id)).scalar() or 0
    return f"NEG-{datetime.now().year}-{str(max_id + 1).zfill(4)}"


def _send_negotiation_email(vendor, subject: str, neg_ref: str):
    """Fire negotiation invite / price-revision email to vendor (simulated)."""
    import os, logging
    logger = logging.getLogger(__name__)
    platform_url = os.getenv("PLATFORM_URL", "http://127.0.0.1:5500/frontend/pages")
    portal_link  = f"{platform_url}/vendor_portal.html"

    print(
        f"\n[NEGOTIATION EMAIL]\n"
        f"   To      : {vendor.email} ({vendor.company_name})\n"
        f"   Subject : {subject}\n"
        f"   Ref     : {neg_ref}\n"
        f"   Action  : Vendor is requested to revise their item-wise prices\n"
        f"   Portal  : {portal_link}\n"
    )
    logger.info(
        f"[NEG EMAIL SIMULATED] {neg_ref} -> {vendor.email} | {subject}"
    )


# ── GET all negotiations ───────────────────────────────────────────────────────

@router.get("/")
def get_negotiations(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Negotiation)
    if status:
        query = query.filter(Negotiation.status == status)
    negs = query.order_by(Negotiation.created_at.desc()).all()
    result = []
    for n in negs:
        vendor = db.query(Vendor).filter(Vendor.id == n.vendor_id).first()
        neg_items = db.query(NegotiationItem).filter(NegotiationItem.negotiation_id == n.id).all()
        result.append({
            "id"                 : n.id,
            "negotiation_ref"    : n.negotiation_ref,
            "vendor_name"        : vendor.company_name if vendor else "Unknown",
            "vendor_id"          : n.vendor_id,
            "subject"            : n.subject,
            "quotation_id"       : n.quotation_id,
            "po_id"              : n.po_id,
            "initial_price"      : float(n.initial_price or 0),
            "target_price"       : float(n.target_price or 0),
            "agreed_price"       : float(n.agreed_price or 0) if n.agreed_price else None,
            "savings_achieved"   : float(n.savings_achieved or 0),
            "savings_percent"    : float(n.savings_percent or 0),
            "payment_terms"      : n.payment_terms,
            "delivery_commitment": n.delivery_commitment,
            "warranty_terms"     : n.warranty_terms,
            "status"             : n.status,
            "outcome_notes"      : n.outcome_notes,
            "negotiated_by"      : n.negotiated_by,
            "created_at"         : str(n.created_at),
            "items"              : [
                {
                    "id"                : ni.id,
                    "description"       : ni.description,
                    "quantity"          : float(ni.quantity),
                    "unit"              : ni.unit,
                    "initial_unit_price": float(ni.initial_unit_price),
                    "target_unit_price" : float(ni.target_unit_price) if ni.target_unit_price else None,
                    "agreed_unit_price" : float(ni.agreed_unit_price) if ni.agreed_unit_price else None,
                    "tax_percent"       : float(ni.tax_percent),
                    "quotation_item_id" : ni.quotation_item_id,
                    "line_total_initial": round(float(ni.quantity) * float(ni.initial_unit_price) * (1 + float(ni.tax_percent)/100), 2),
                    "line_total_agreed" : round(float(ni.quantity) * float(ni.agreed_unit_price) * (1 + float(ni.tax_percent)/100), 2) if ni.agreed_unit_price else None,
                }
                for ni in neg_items
            ]
        })
    total_savings = sum(r["savings_achieved"] for r in result)
    return {"total": len(result), "total_savings_inr": total_savings, "negotiations": result}


# ── POST create negotiation ────────────────────────────────────────────────────

@router.post("/")
def create_negotiation(data: NegotiationCreate, db: Session = Depends(get_db)):
    neg = Negotiation(
        negotiation_ref     = gen_neg_ref(db),
        vendor_id           = data.vendor_id,
        rfq_id              = data.rfq_id,
        quotation_id        = data.quotation_id,
        po_id               = data.po_id,
        subject             = data.subject,
        initial_price       = data.initial_price,
        target_price        = data.target_price,
        payment_terms       = data.payment_terms,
        delivery_commitment = data.delivery_commitment,
        warranty_terms      = data.warranty_terms,
        negotiated_by       = data.negotiated_by,
        status              = "Open"
    )
    db.add(neg)
    db.flush()

    # ── Auto-load items from quotation if quotation_id provided ──────────────
    items_to_add = data.items or []
    if data.quotation_id and not items_to_add:
        q_items = db.query(QuotationItem).filter(
            QuotationItem.quotation_id == data.quotation_id
        ).all()
        for qi in q_items:
            items_to_add.append(NegotiationItemIn(
                description        = qi.description,
                quantity           = float(qi.quantity),
                unit               = "PCS",
                initial_unit_price = float(qi.unit_price),
                target_unit_price  = None,
                tax_percent        = float(qi.tax_percent),
                quotation_item_id  = qi.id
            ))

    for item in items_to_add:
        db.add(NegotiationItem(
            negotiation_id     = neg.id,
            quotation_item_id  = item.quotation_item_id,
            description        = item.description,
            quantity           = item.quantity,
            unit               = item.unit or "PCS",
            initial_unit_price = item.initial_unit_price,
            target_unit_price  = item.target_unit_price,
            agreed_unit_price  = None,
            tax_percent        = item.tax_percent or 18.0
        ))

    db.commit()
    db.refresh(neg)

    # ── Email trigger ─────────────────────────────────────────────────────────
    vendor = db.query(Vendor).filter(Vendor.id == data.vendor_id).first()
    if vendor:
        _send_negotiation_email(
            vendor  = vendor,
            subject = data.subject,
            neg_ref = neg.negotiation_ref
        )

    return {"message": "Negotiation started", "ref": neg.negotiation_ref, "id": neg.id}


# ── GET quotation items for negotiation modal ──────────────────────────────────

@router.get("/quotation-items/{quotation_id}")
def get_quotation_items_for_neg(quotation_id: int, db: Session = Depends(get_db)):
    """Returns quotation items pre-formatted for the negotiation start modal."""
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation_id).all()
    quot  = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quot:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {
        "quotation_id"    : quotation_id,
        "quotation_number": quot.quotation_number,
        "total_amount"    : float(quot.total_amount or 0),
        "items": [
            {
                "id"            : qi.id,
                "description"   : qi.description,
                "quantity"      : float(qi.quantity),
                "unit_price"    : float(qi.unit_price),
                "tax_percent"   : float(qi.tax_percent),
                "total_price"   : float(qi.total_price),
            }
            for qi in items
        ]
    }


# ── PATCH close / agree negotiation ───────────────────────────────────────────

@router.patch("/{neg_id}/close")
def close_negotiation(neg_id: int, data: NegotiationUpdate, db: Session = Depends(get_db)):
    neg = db.query(Negotiation).filter(Negotiation.id == neg_id).first()
    if not neg:
        raise HTTPException(status_code=404, detail="Negotiation not found")

    # ── Step 1: Update item-wise agreed prices ────────────────────────────────
    if data.items:
        for item_close in data.items:
            neg_item = db.query(NegotiationItem).filter(
                NegotiationItem.id == item_close.negotiation_item_id,
                NegotiationItem.negotiation_id == neg_id
            ).first()
            if neg_item:
                neg_item.agreed_unit_price = item_close.agreed_unit_price

        # Recalculate agreed_price from items
        all_items = db.query(NegotiationItem).filter(NegotiationItem.negotiation_id == neg_id).all()
        recalc_total = sum(
            float(ni.quantity) * float(ni.agreed_unit_price or ni.initial_unit_price) * (1 + float(ni.tax_percent)/100)
            for ni in all_items
        )
        neg.agreed_price = recalc_total
    elif data.agreed_price:
        neg.agreed_price = data.agreed_price

    # ── Step 2: Compute savings ───────────────────────────────────────────────
    if neg.agreed_price and neg.initial_price:
        savings           = float(neg.initial_price) - float(neg.agreed_price)
        neg.savings_achieved = max(savings, 0)
        neg.savings_percent  = round((neg.savings_achieved / float(neg.initial_price)) * 100, 2) if neg.initial_price else 0

    # ── Step 3: Update other fields ───────────────────────────────────────────
    for field, value in data.dict(exclude_none=True).items():
        if field not in ["agreed_price", "items"]:
            setattr(neg, field, value)

    neg.updated_at = datetime.utcnow()

    # ── Step 4: If Agreed, cascade negotiated prices back to QuotationItems & PO ──
    if data.status == "Agreed":
        _sync_prices_to_quotation_and_po(neg, db)

    db.commit()
    return {
        "message"         : "Negotiation updated",
        "savings_achieved": float(neg.savings_achieved or 0),
        "savings_percent" : float(neg.savings_percent or 0),
        "agreed_price"    : float(neg.agreed_price or 0)
    }


def _sync_prices_to_quotation_and_po(neg: Negotiation, db: Session):
    """
    When negotiation is Agreed:
    1. Update QuotationItem unit_prices to agreed values
    2. Recalculate Quotation totals
    3. Update linked POItem unit_prices and PO total_amount
    """
    neg_items = db.query(NegotiationItem).filter(NegotiationItem.negotiation_id == neg.id).all()

    # Update quotation items
    for ni in neg_items:
        if ni.quotation_item_id and ni.agreed_unit_price:
            qi = db.query(QuotationItem).filter(QuotationItem.id == ni.quotation_item_id).first()
            if qi:
                qi.unit_price  = ni.agreed_unit_price
                qi.total_price = float(ni.quantity) * float(ni.agreed_unit_price) * (1 + float(ni.tax_percent or 18) / 100)

    # Recalculate Quotation header totals
    if neg.quotation_id:
        quot = db.query(Quotation).filter(Quotation.id == neg.quotation_id).first()
        if quot:
            all_qi    = db.query(QuotationItem).filter(QuotationItem.quotation_id == quot.id).all()
            new_sub   = sum(float(qi.quantity) * float(qi.unit_price) for qi in all_qi)
            new_tax   = sum(float(qi.quantity) * float(qi.unit_price) * float(qi.tax_percent or 18) / 100 for qi in all_qi)
            quot.subtotal     = new_sub
            quot.tax_amount   = new_tax
            quot.total_amount = new_sub + new_tax

            # Now update linked PO if it exists
            po = db.query(PurchaseOrder).filter(PurchaseOrder.quotation_id == quot.id).first()
            if po:
                # Match POItems to QuotationItems by description
                po_items = db.query(POItem).filter(POItem.po_id == po.id).all()
                for ni in neg_items:
                    if ni.agreed_unit_price:
                        for pi in po_items:
                            if pi.description == ni.description:
                                pi.unit_price  = ni.agreed_unit_price
                                pi.total_price = float(ni.quantity) * float(ni.agreed_unit_price) * (1 + float(ni.tax_percent or 18) / 100)
                                break

                # Recalculate PO totals
                new_po_sub = sum(float(pi.quantity) * float(pi.unit_price) for pi in po_items)
                new_po_tax = sum(float(pi.quantity) * float(pi.unit_price) * float(pi.tax_percent or 18) / 100 for pi in po_items)
                po.subtotal     = new_po_sub
                po.tax_amount   = new_po_tax
                po.total_amount = new_po_sub + new_po_tax
                po.notes        = (po.notes or "") + f"\n[Updated from Negotiation {neg.negotiation_ref} — prices revised post-negotiation]"

    db.flush()


# ── GET summary ────────────────────────────────────────────────────────────────

@router.get("/summary")
def negotiation_summary(db: Session = Depends(get_db)):
    """Overall savings tracking — BR-S2P-06"""
    from sqlalchemy import func
    negs = db.query(Negotiation).filter(Negotiation.status == "Agreed").all()
    total_initial = sum(float(n.initial_price or 0) for n in negs)
    total_agreed  = sum(float(n.agreed_price  or 0) for n in negs if n.agreed_price)
    total_savings = total_initial - total_agreed
    return {
        "total_negotiations"   : len(negs),
        "total_initial_value"  : round(total_initial, 2),
        "total_agreed_value"   : round(total_agreed,  2),
        "total_savings_inr"    : round(total_savings,  2),
        "avg_savings_percent"  : round(
            sum(float(n.savings_percent or 0) for n in negs) / len(negs), 2
        ) if negs else 0
    }


@router.get("/chart-data/")
def get_chart_data(db: Session = Depends(get_db)):
    """Fetch monthly aggregation for dashboard charts"""
    from collections import defaultdict
    negs = db.query(Negotiation).filter(Negotiation.status == "Agreed").order_by(Negotiation.created_at.asc()).all()
    grouped = defaultdict(lambda: {"initial": 0.0, "agreed": 0.0, "savings": 0.0})
    for n in negs:
        if not n.created_at: continue
        month_str = n.created_at.strftime("%b %Y")
        grouped[month_str]["initial"] += float(n.initial_price or 0)
        grouped[month_str]["agreed"]  += float(n.agreed_price  or 0)
        grouped[month_str]["savings"] += float(n.savings_achieved or 0)
    labels = list(grouped.keys())
    return {
        "labels"  : labels,
        "initial" : [grouped[m]["initial"] for m in labels],
        "agreed"  : [grouped[m]["agreed"]  for m in labels],
        "savings" : [grouped[m]["savings"] for m in labels]
    }