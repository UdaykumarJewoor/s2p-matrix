# routers/workflow.py
# Full S2P Lifecycle Automation Endpoints
# BR-S2P-01 through BR-S2P-11 — end-to-end pipeline
# Matrix Comsec Pvt. Ltd.

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.rfq import RFQ, RFQItem
from app.models.invoice import Invoice, GRN
from app.models.purchase_order import PurchaseOrder
from app.models.payment import Payment
from app.models.vendor import Vendor
from app.services.rfq_engine import run_rfq_pipeline
from app.services.invoice_matcher import run_three_way_match, get_unmatched_invoices
from app.services.vendor_scorer import score_vendor
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, timedelta
import logging
import random

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic Schemas ─────────────────────────────────────────

class WorkflowRunRequest(BaseModel):
    rfq_id       : int
    strategy     : Optional[str] = "best_value"   # "best_value" or "lowest_cost"
    top_vendors  : Optional[int] = 7

class CompleteWorkflowRequest(BaseModel):
    po_id            : int
    quality_status   : Optional[str] = "Accepted"    # Accepted / Partially Accepted / Rejected
    received_by      : Optional[str] = "Warehouse Team"
    payment_mode     : Optional[str] = "NEFT"

class BatchMatchRequest(BaseModel):
    invoice_ids: List[int]


# ── Helper ───────────────────────────────────────────────────

def _generate_ref(prefix: str, db: Session, model) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(model.id)).scalar() or 0
    return f"{prefix}-{year}-{str(max_id + 1).zfill(4)}"


# ── ROUTES ───────────────────────────────────────────────────

@router.post("/run", summary="Stage 1–5: RFQ → Discovery → Quotes → Compare → PO")
def run_full_pipeline(data: WorkflowRunRequest, db: Session = Depends(get_db)):
    """
    Runs the automated procurement pipeline:
      Stage 1 — Load & validate RFQ
      Stage 2 — AI Vendor Discovery (category-based, top N vendors)
      Stage 3 — Auto-generate simulated quotations
      Stage 4 — AI quotation comparison & vendor selection
      Stage 5 — Auto-create Purchase Order

    Returns full structured audit JSON with per-stage timing & results.
    """
    try:
        result = run_rfq_pipeline(
            rfq_id      = data.rfq_id,
            db          = db,
            strategy    = data.strategy or "best_value",
            top_vendors = data.top_vendors or 7
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Pipeline failed for RFQ {data.rfq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.get("/status/{rfq_id}", summary="Unified Status: Scan real-world progress (manual/auto)")
def get_rfq_pipeline_status(rfq_id: int, db: Session = Depends(get_db)):
    """
    Scans the entire database across all tables (RFQ -> Quote -> PO -> Receipt -> Invoice -> Payment)
    to detect the current state of a procurement journey, regardless of manual or automated origin.
    """
    # ── Stage 1: RFQ ──
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail=f"RFQ {rfq_id} not found")
    
    # ── Stage 2-3: Quotations ──
    from app.models.quotation import Quotation
    quotes = db.query(Quotation).filter(Quotation.rfq_id == rfq_id).all()
    
    # ── Stage 5: PO ──
    po = db.query(PurchaseOrder).filter(PurchaseOrder.rfq_id == rfq_id).first()
    
    # ── Stage 6: GRN ──
    grn = None
    if po:
        grn = db.query(GRN).filter(GRN.po_id == po.id).first()
        
    # ── Stage 7: Invoice ──
    invoice = None
    if po:
        invoice = db.query(Invoice).filter(Invoice.po_id == po.id).first()
        
    # ── Stage 8: Payment ──
    payment = None
    if invoice:
        payment = db.query(Payment).filter(Payment.invoice_id == invoice.id).first()

    # ── Build Audit ──
    audit = {
        "rfq_id" : rfq_id,
        "stages" : {
            "stage_1_rfq": {
                "status": "✅ Completed",
                "rfq_number": rfq.rfq_number,
                "title": rfq.title,
                "items_count": len(rfq.items) if rfq.items else 0
            },
            "stage_2_3_quotes": {
                "status": "✅ Completed" if quotes else "⌛ Pending",
                "count": len(quotes)
            },
            "stage_4_comparison": {
                "status": "✅ Completed" if any(q.status == "Selected" for q in quotes) else "⌛ Pending"
            },
            "stage_5_po": {
                "status": "✅ Completed" if po else "⌛ Pending",
                "po_id": po.id if po else None,
                "po_number": po.po_number if po else None,
                "po_status": po.status if po else None
            },
            "stage_6_grn": {
                "status": "✅ Completed" if grn else "⌛ Pending",
                "grn_number": grn.grn_number if grn else None,
                "received_date": str(grn.received_date) if grn else None
            },
            "stage_7_invoice": {
                "status": "✅ Completed" if invoice else "⌛ Pending",
                "internal_ref": invoice.internal_ref if invoice else None,
                "match_status": invoice.match_status if invoice else "Pending"
            },
            "stage_8_payment": {
                "status": "✅ Completed" if (payment or (invoice and invoice.payment_status == 'Paid')) else "⌛ Pending",
                "payment_ref": payment.payment_reference if payment else None
            }
        }
    }
    
    # Logic for summarizing the next action
    if not po:
        audit["next_action"] = "RUN_1_5"
    elif not payment:
        audit["next_action"] = "COMPLETE_6_8"
    else:
        audit["next_action"] = "FINISHED"

    return audit


@router.post("/complete", summary="Stage 6–8: GRN → Invoice → 3-Way Match → Payment → Score")
def complete_po_lifecycle(data: CompleteWorkflowRequest, db: Session = Depends(get_db)):
    """
    State-aware completion of the post-PO lifecycle.
    Reads the RFQ's current stage first — skips any stage already completed
    by manual action (e.g., warehouse Receive button, manual invoice upload).
    Always continues forward from the last completed stage.
    """
    from app.services.rfq_stage_engine import get_rfq_current_stage, advance_rfq_stage

    pipeline_start = datetime.utcnow()
    audit = {
        "pipeline_id": f"COMP-{data.po_id}-{int(pipeline_start.timestamp())}",
        "po_id"      : data.po_id,
        "started_at" : str(pipeline_start),
        "stages"     : {}
    }

    # ── Load PO + resolve RFQ context ───────────────────────────
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == data.po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail=f"Purchase Order {data.po_id} not found")

    rfq_id = po.rfq_id
    # Detect true current stage from DB facts (manual OR pipeline)
    detected_stage = get_rfq_current_stage(rfq_id, db) if rfq_id else 5
    audit["rfq_id"]                 = rfq_id
    audit["detected_stage_on_entry"] = detected_stage

    # ── STAGE 6: GRN ────────────────────────────────────────────
    t0           = datetime.utcnow()
    existing_grn = db.query(GRN).filter(GRN.po_id == data.po_id).first()

    if existing_grn:
        grn        = existing_grn
        grn_status = "already_exists"
        if rfq_id:
            advance_rfq_stage(rfq_id, 6, db)   # ensure stage is recorded even if GRN was manual
    else:
        delivery_offset = random.randint(-2, 3)
        received_date   = (po.delivery_date + timedelta(days=delivery_offset)
                           if po.delivery_date else date.today())
        if received_date > date.today():
            received_date = date.today()

        grn = GRN(
            grn_number    = _generate_ref("GRN", db, GRN),
            po_id         = po.id,
            vendor_id     = po.vendor_id,
            received_date = received_date,
            received_by   = data.received_by,
            quality_status= data.quality_status,
            notes         = f"Auto-created via S2P completion pipeline. PO: {po.po_number}"
        )
        db.add(grn)
        po.status = "Received" if data.quality_status == "Accepted" else "Partially Received"
        db.commit()
        db.refresh(grn)
        grn_status = "created"
        if rfq_id:
            advance_rfq_stage(rfq_id, 6, db)

    audit["stages"]["stage_6_grn"] = {
        "status"        : "⏩ Using existing GRN" if grn_status == "already_exists" else "✅ Completed",
        "duration_ms"   : int((datetime.utcnow() - t0).total_seconds() * 1000),
        "grn_number"    : grn.grn_number,
        "received_date" : str(grn.received_date),
        "quality_status": grn.quality_status,
        "action"        : grn_status
    }

    # ── STAGE 7: Invoice + 3-Way Match ─────────────────────────
    t0           = datetime.utcnow()
    existing_inv = db.query(Invoice).filter(Invoice.po_id == po.id).first()

    if existing_inv:
        invoice    = existing_inv
        inv_status = "already_exists"
        # Link GRN to invoice if not already linked
        if not invoice.grn_id:
            invoice.grn_id = grn.id
            db.commit()
    else:
        invoice_number = f"INV-{po.vendor_id}-{datetime.now().strftime('%Y%m%d%H%M')}"
        due_date       = date.today() + timedelta(days=30)
        invoice = Invoice(
            invoice_number = invoice_number,
            internal_ref   = _generate_ref("INV", db, Invoice),
            vendor_id      = po.vendor_id,
            po_id          = po.id,
            grn_id         = grn.id,
            invoice_date   = date.today(),
            received_date  = date.today(),
            due_date       = due_date,
            subtotal       = float(po.subtotal),
            tax_amount     = float(po.tax_amount),
            total_amount   = float(po.total_amount),
            status         = "Received",
            match_status   = "Pending",
            payment_status = "Unpaid"
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        inv_status = "created"

    # Always re-run 3-way match (GRN may have just been linked)
    match_result = run_three_way_match(invoice.id, db)
    if rfq_id and match_result.get("match_status") in ("Matched", "Partial Match"):
        advance_rfq_stage(rfq_id, 7, db)

    audit["stages"]["stage_7_invoice_match"] = {
        "status"        : "⏩ Used existing invoice + re-matched" if inv_status == "already_exists" else "✅ Completed",
        "duration_ms"   : int((datetime.utcnow() - t0).total_seconds() * 1000),
        "internal_ref"  : invoice.internal_ref,
        "invoice_number": invoice.invoice_number,
        "total_amount"  : float(invoice.total_amount),
        "action"        : inv_status,
        "match_result"  : match_result
    }

    # ── STAGE 8: Payment + Vendor Score ─────────────────────────
    t0 = datetime.utcnow()
    if match_result["match_status"] in ("Matched", "Partial Match"):
        existing_pay = db.query(Payment).filter(Payment.invoice_id == invoice.id).first()

        if existing_pay:
            payment    = existing_pay
            pay_status = "already_exists"
        else:
            payment = Payment(
                payment_ref    = _generate_ref("PAY", db, Payment),
                invoice_id     = invoice.id,
                vendor_id      = po.vendor_id,
                amount         = float(invoice.total_amount),
                currency       = "INR",
                payment_mode   = data.payment_mode,
                payment_date   = date.today(),
                value_date     = date.today(),
                bank_reference = f"NEFT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                status         = "Processed",
                notes          = f"Auto-payment via S2P pipeline for PO {po.po_number}"
            )
            db.add(payment)
            invoice.payment_status = "Paid"
            invoice.status         = "Paid"
            db.commit()
            db.refresh(payment)
            pay_status = "processed"
            if rfq_id:
                advance_rfq_stage(rfq_id, 8, db)

        score_result = score_vendor(po.vendor_id, db)
        audit["stages"]["stage_8_payment_score"] = {
            "status"              : "⏩ Payment already existed" if pay_status == "already_exists" else "✅ Completed",
            "duration_ms"         : int((datetime.utcnow() - t0).total_seconds() * 1000),
            "payment_ref"         : payment.payment_ref,
            "amount_paid_inr"     : float(payment.amount),
            "payment_mode"        : payment.payment_mode,
            "payment_action"      : pay_status,
            "vendor_score_updated": {
                "vendor_id"       : po.vendor_id,
                "vendor_name"     : score_result.get("vendor_name"),
                "new_overall_score": score_result.get("overall_score"),
                "grade"           : score_result.get("grade"),
            }
        }
    else:
        audit["stages"]["stage_8_payment_score"] = {
            "status": "⏸️ HELD",
            "reason": f"Payment on hold — Match status: {match_result['match_status']}",
            "action": match_result.get("recommendation")
        }

    audit["completed_at"]      = str(datetime.utcnow())
    audit["total_duration_ms"] = int((datetime.utcnow() - pipeline_start).total_seconds() * 1000)
    st8 = audit["stages"].get("stage_8_payment_score", {})
    if "✅" in st8.get("status", "") or "⏩" in st8.get("status", ""):
        audit["result"] = "✅ LIFECYCLE COMPLETE — Payment processed & vendor score updated"
    else:
        audit["result"] = f"⚠️ PARTIAL — {st8.get('reason', 'Review required')}"

    return audit

@router.post("/match/batch", summary="Run 3-way match on multiple invoices")
def batch_invoice_match(data: BatchMatchRequest, db: Session = Depends(get_db)):
    """Batch 3-way match for a list of invoice IDs."""
    from app.services.invoice_matcher import batch_match_invoices
    results = batch_match_invoices(data.invoice_ids, db)
    matched   = sum(1 for r in results if r.get("match_status") == "Matched")
    mismatched = sum(1 for r in results if r.get("match_status") == "Mismatch")
    return {
        "total_processed": len(results),
        "matched"        : matched,
        "partial"        : len(results) - matched - mismatched,
        "mismatched"     : mismatched,
        "results"        : results
    }


@router.get("/match/pending", summary="List all invoices pending 3-way match")
def get_pending_matches(db: Session = Depends(get_db)):
    """Returns invoices that still need the 3-way match to be run."""
    items = get_unmatched_invoices(db)
    return {"total": len(items), "invoices": items}


@router.get("/summary", summary="S2P system-wide procurement summary")
def get_workflow_summary(db: Session = Depends(get_db)):
    """High-level KPI summary of the entire S2P pipeline state."""
    from app.models.quotation import Quotation

    total_rfq     = db.query(func.count(RFQ.id)).scalar() or 0
    open_rfq      = db.query(func.count(RFQ.id)).filter(
        RFQ.status.in_(["Draft", "Sent", "Responses Received", "Evaluation"])
    ).scalar() or 0
    total_po      = db.query(func.count(PurchaseOrder.id)).scalar() or 0
    total_po_val  = db.query(func.sum(PurchaseOrder.total_amount)).filter(
        PurchaseOrder.status.notin_(["Cancelled"])
    ).scalar() or 0
    total_invoices = db.query(func.count(Invoice.id)).scalar() or 0
    unmatched_inv  = db.query(func.count(Invoice.id)).filter(
        Invoice.match_status.in_(["Pending", "Mismatch"])
    ).scalar() or 0
    total_paid     = db.query(func.sum(Payment.amount)).filter(
        Payment.status == "Processed"
    ).scalar() or 0
    total_vendors  = db.query(func.count(Vendor.id)).filter(
        Vendor.status == "Approved"
    ).scalar() or 0

    return {
        "procurement_kpis": {
            "total_rfqs"           : total_rfq,
            "open_rfqs"            : open_rfq,
            "total_purchase_orders": total_po,
            "total_po_value_inr"   : float(total_po_val),
            "total_invoices"       : total_invoices,
            "unmatched_invoices"   : unmatched_inv,
            "total_payments_inr"   : float(total_paid),
            "approved_vendors"     : total_vendors,
        },
        "pipeline_health": {
            "invoice_match_rate_pct": round(
                ((total_invoices - unmatched_inv) / total_invoices * 100)
                if total_invoices else 100, 1
            ),
            "automation_coverage": "Stage 1–8 fully automated",
            "brd_compliance"     : "BR-S2P-01 to BR-S2P-13 active"
        }
    }
