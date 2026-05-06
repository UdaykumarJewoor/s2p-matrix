# services/vendor_scorer.py
# BR-S2P-13: Automated vendor performance scoring
# Uses rule-based logic + weighted scoring (no paid AI needed)

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder
from app.models.invoice import Invoice, GRN
from app.models.payment import Payment, VendorPerformance
from app.models.rfq import RFQ, RFQVendor
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ── Scoring Weights (must sum to 100) ────────────────────────
WEIGHTS = {
    "delivery" : 35,   # On-time delivery is most critical
    "quality"  : 30,   # Quality acceptance rate
    "pricing"  : 20,   # Price competitiveness
    "response" : 15,   # RFQ response rate
}

def calculate_delivery_score(vendor_id: int, db: Session) -> tuple:
    """Score based on on-time PO delivery (0-100)"""
    total_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.vendor_id == vendor_id,
        PurchaseOrder.status.in_(["Received", "Closed"])
    ).count()

    if total_pos == 0:
        return 50.0, total_pos, 0   # neutral score if no history

    # Count GRNs received on or before PO delivery date
    on_time = 0
    pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.vendor_id == vendor_id,
        PurchaseOrder.status.in_(["Received", "Closed"])
    ).all()

    for po in pos:
        if not po.delivery_date:
            on_time += 1   # no date set = assume on time
            continue
        grn = db.query(GRN).filter(GRN.po_id == po.id).first()
        if grn and grn.received_date <= po.delivery_date:
            on_time += 1

    score = round((on_time / total_pos) * 100, 2)
    return score, total_pos, on_time


def calculate_quality_score(vendor_id: int, db: Session) -> tuple:
    """Score based on GRN acceptance rate (0-100)"""
    grns = db.query(GRN).filter(GRN.vendor_id == vendor_id).all()

    if not grns:
        return 50.0, 0   # neutral if no GRNs

    rejected = sum(1 for g in grns if g.quality_status == "Rejected")
    partial  = sum(1 for g in grns if g.quality_status == "Partially Accepted")
    total    = len(grns)

    # Rejected = -1 point, Partial = -0.5 point
    penalty  = (rejected * 1.0) + (partial * 0.5)
    score    = max(0, round(((total - penalty) / total) * 100, 2))
    return score, rejected


def calculate_pricing_score(vendor_id: int, db: Session, all_vendor_ids: list) -> float:
    """
    Score based on price competitiveness vs other vendors.
    Compares average PO value per item against peer vendors.
    """
    if len(all_vendor_ids) <= 1:
        return 70.0   # only vendor, give decent score

    # Get average PO total for this vendor
    my_avg = db.query(func.avg(PurchaseOrder.total_amount)).filter(
        PurchaseOrder.vendor_id == vendor_id,
        PurchaseOrder.status.notin_(["Cancelled", "Draft"])
    ).scalar()

    if not my_avg:
        return 50.0

    # Get average across all vendors
    all_avg = db.query(func.avg(PurchaseOrder.total_amount)).filter(
        PurchaseOrder.vendor_id.in_(all_vendor_ids),
        PurchaseOrder.status.notin_(["Cancelled", "Draft"])
    ).scalar()

    if not all_avg or float(all_avg) == 0:
        return 50.0

    ratio = float(my_avg) / float(all_avg)

    # Lower price = higher score
    if ratio <= 0.8:   return 100.0
    elif ratio <= 0.9: return 90.0
    elif ratio <= 1.0: return 75.0
    elif ratio <= 1.1: return 60.0
    elif ratio <= 1.2: return 45.0
    else:              return 25.0


def calculate_response_score(vendor_id: int, db: Session) -> tuple:
    """Score based on RFQ response rate (0-100)"""
    rfq_sent = db.query(RFQVendor).filter(
        RFQVendor.vendor_id == vendor_id
    ).count()

    if rfq_sent == 0:
        return 50.0, 0, 0   # no RFQs sent yet

    responded = db.query(RFQVendor).filter(
        RFQVendor.vendor_id  == vendor_id,
        RFQVendor.response_status == "Responded"
    ).count()

    score = round((responded / rfq_sent) * 100, 2)
    return score, rfq_sent, responded


def score_vendor(vendor_id: int, db: Session,
                 period: str = None) -> dict:
    """
    Master scoring function — calculates all 4 KPIs
    and saves to vendor_performance table.
    Returns the score dict.
    """
    if not period:
        now    = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        period  = f"Q{quarter}-{now.year}"

    # Get all approved vendor IDs for pricing comparison
    all_vendor_ids = [
        v.id for v in db.query(Vendor.id).filter(
            Vendor.status == "Approved"
        ).all()
    ]

    # Calculate each KPI
    delivery_score, total_orders, on_time = calculate_delivery_score(vendor_id, db)
    quality_score,  rejections            = calculate_quality_score(vendor_id, db)
    pricing_score                         = calculate_pricing_score(vendor_id, db, all_vendor_ids)
    response_score, rfqs_recv, rfqs_resp  = calculate_response_score(vendor_id, db)

    # ── Day-Zero Profile Intelligence ───────────────────────────
    # If a vendor is new (no orders/history), we calculate a Profile Confidence Score
    # instead of just serving a neutral 50.
    is_new = (total_orders == 0 and rfqs_recv == 0)
    
    if is_new:
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        profile_score = 40.0 # base score
        if vendor:
            if vendor.oem_approved:    profile_score += 20.0 # Trust boost
            if vendor.gst_number:      profile_score += 10.0 # Compliance boost
            if vendor.pan_number:      profile_score += 10.0 # Documentation boost
            if vendor.msme_registered: profile_score += 10.0 # Governance boost
        
        # Override KPIs for the initial rank
        delivery_score = profile_score
        quality_score  = profile_score
        pricing_score  = profile_score
        response_score = profile_score

    # Weighted overall score
    overall = round(
        (delivery_score * WEIGHTS["delivery"] / 100) +
        (quality_score  * WEIGHTS["quality"]  / 100) +
        (pricing_score  * WEIGHTS["pricing"]  / 100) +
        (response_score * WEIGHTS["response"] / 100),
        2
    )

    # Grade
    if overall >= 85:   grade = "A+ (Excellent)"
    elif overall >= 75: grade = "A  (Good)"
    elif overall >= 60: grade = "B  (Average)"
    elif overall >= 45: grade = "C  (Below Average)"
    else:               grade = "D  (Poor — Review Required)"

    # Upsert into vendor_performance table
    existing = db.query(VendorPerformance).filter(
        VendorPerformance.vendor_id        == vendor_id,
        VendorPerformance.evaluation_period == period
    ).first()

    if existing:
        perf = existing
    else:
        perf = VendorPerformance(vendor_id=vendor_id, evaluation_period=period)
        db.add(perf)

    perf.delivery_score     = delivery_score
    perf.quality_score      = quality_score
    perf.pricing_score      = pricing_score
    perf.response_score     = response_score
    perf.overall_score      = overall
    perf.total_orders       = total_orders
    perf.on_time_deliveries = on_time
    perf.quality_rejections = rejections
    perf.rfqs_received      = rfqs_recv
    perf.rfqs_responded     = rfqs_resp
    perf.evaluated_at       = datetime.utcnow()

    # Update vendor's main performance_score field
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if vendor:
        vendor.performance_score = overall

    db.commit()

    return {
        "vendor_id"        : vendor_id,
        "vendor_name"      : vendor.company_name if vendor else "Unknown",
        "period"           : period,
        "delivery_score"   : delivery_score,
        "quality_score"    : quality_score,
        "pricing_score"    : pricing_score,
        "response_score"   : response_score,
        "overall_score"    : overall,
        "grade"            : grade,
        "total_orders"     : total_orders,
        "on_time_deliveries": on_time,
        "quality_rejections": rejections,
        "rfqs_received"    : rfqs_recv,
        "rfqs_responded"   : rfqs_resp,
        "weights_used"     : WEIGHTS
    }


def score_all_vendors(db: Session) -> list:
    """Run scoring for ALL approved vendors at once"""
    vendors = db.query(Vendor).filter(
        Vendor.status == "Approved"
    ).all()

    results = []
    for v in vendors:
        try:
            result = score_vendor(v.id, db)
            results.append(result)
            logger.info(f"Scored vendor {v.vendor_code}: {result['overall_score']}")
        except Exception as e:
            logger.error(f"Failed to score vendor {v.id}: {e}")

    # Sort by overall score descending
    results.sort(key=lambda x: x["overall_score"], reverse=True)
    return results