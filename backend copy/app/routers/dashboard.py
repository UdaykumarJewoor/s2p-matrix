# routers/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.vendor import Vendor
from app.models.rfq import RFQ
from app.models.quotation import Quotation
from app.models.purchase_order import PurchaseOrder
from app.models.invoice import Invoice
from app.models.payment import Payment

router = APIRouter()

@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Main dashboard — spend, vendor, RFQ, invoice KPIs (BR-S2P-08)"""

    total_vendors    = db.query(func.count(Vendor.id)).scalar()
    approved_vendors = db.query(func.count(Vendor.id)).filter(
                           Vendor.status == "Approved").scalar()
    pending_vendors  = db.query(func.count(Vendor.id)).filter(
                           Vendor.status == "Pending").scalar()

    total_rfqs  = db.query(func.count(RFQ.id)).scalar()
    open_rfqs   = db.query(func.count(RFQ.id)).filter(
                      RFQ.status.in_(["Draft", "Sent", "Responses Received"])).scalar()

    total_pos    = db.query(func.count(PurchaseOrder.id)).scalar()
    pending_pos  = db.query(func.count(PurchaseOrder.id)).filter(
                       PurchaseOrder.status.in_(
                           ["Pending L1 Approval", "Pending L2 Approval"])).scalar()
    total_spend  = db.query(func.sum(PurchaseOrder.total_amount)).filter(
                       PurchaseOrder.status.in_(["Approved", "Sent to Vendor", "Acknowledged", "Partially Received", "Received", "Closed"])
                   ).scalar() or 0

    total_invoices    = db.query(func.count(Invoice.id)).scalar()
    unmatched_invoices = db.query(func.count(Invoice.id))\
                             .join(PurchaseOrder, Invoice.po_id == PurchaseOrder.id)\
                             .filter(
                                 Invoice.match_status.in_(["Pending", "Mismatch", "Exception"]),
                                 PurchaseOrder.status.notin_(["Received", "Closed"])
                             ).scalar()
    unpaid_invoices   = db.query(func.count(Invoice.id)).filter(
                             Invoice.payment_status == "Unpaid").scalar()
    unpaid_amount     = db.query(func.sum(Invoice.total_amount)).filter(
                             Invoice.payment_status == "Unpaid").scalar() or 0

    total_payments = db.query(func.sum(Payment.amount)).filter(
                         Payment.status == "Processed").scalar() or 0

    return {
        "vendors": {
            "total"   : total_vendors,
            "approved": approved_vendors,
            "pending" : pending_vendors
        },
        "rfq": {
            "total": total_rfqs,
            "open" : open_rfqs
        },
        "purchase_orders": {
            "total"          : total_pos,
            "pending_approval": pending_pos,
            "total_spend_inr" : float(total_spend)
        },
        "invoices": {
            "total"    : total_invoices,
            "unmatched": unmatched_invoices,
            "unpaid"   : unpaid_invoices,
            "unpaid_amount_inr": float(unpaid_amount)
        },
        "payments": {
            "total_processed_inr": float(total_payments)
        }
    }