# routers/commercial_governance.py  — BR-S2P-08
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.purchase_order import PurchaseOrder
from app.models.rfq import RFQ
from app.models.vendor import Vendor
from app.models.quotation import Quotation

router = APIRouter()


@router.get("/governance-summary")
def get_commercial_governance(db: Session = Depends(get_db)):
    """
    BR-S2P-08 — Commercial Governance Dashboard
    Returns: spend-vs-plan by category, top vendor spend, EBIT margin contribution
    """

    # ── 1. Category-Level Spend vs Plan ──────────────────────────────────────
    # "Plan" = sum of RFQ estimated_value grouped by target_category
    # "Actual" = sum of PO total_amount grouped by vendor.category
    category_rows = (
        db.query(
            Vendor.category.label("category"),
            func.sum(PurchaseOrder.total_amount).label("actual_spend"),
            func.count(PurchaseOrder.id).label("po_count")
        )
        .join(Vendor, PurchaseOrder.vendor_id == Vendor.id)
        .filter(PurchaseOrder.status.in_(["Approved", "Sent to Vendor", "Acknowledged",
                                          "Partially Received", "Received", "Closed"]))
        .group_by(Vendor.category)
        .all()
    )

    # RFQ estimated values per category (used as "Budget/Plan")
    rfq_plan_rows = (
        db.query(
            RFQ.target_category.label("category"),
            func.sum(RFQ.estimated_value).label("planned_budget")
        )
        .filter(RFQ.estimated_value.isnot(None))
        .group_by(RFQ.target_category)
        .all()
    )

    rfq_plan_map = {}
    for row in rfq_plan_rows:
        cat = row.category or "Both"
        rfq_plan_map[cat] = float(row.planned_budget or 0)

    category_data = []
    for row in category_rows:
        cat = row.category or "Both"
        actual = float(row.actual_spend or 0)
        # Derive plan from RFQ estimates; fallback = actual + 20% headroom
        planned = rfq_plan_map.get(cat, 0) or rfq_plan_map.get("Both", 0)
        if planned == 0:
            planned = actual * 1.20  # 20% buffer assumption
        utilisation = round((actual / planned * 100), 1) if planned > 0 else 0
        variance = round(planned - actual, 2)

        category_data.append({
            "category"    : cat,
            "planned_inr" : round(planned, 2),
            "actual_inr"  : round(actual, 2),
            "utilisation_pct": utilisation,
            "variance_inr": variance,
            "po_count"    : row.po_count,
            "status"      : "Over Budget" if actual > planned else "On Track"
        })

    # ── 2. Top Vendor Spend Allocation ──────────────────────────────────────
    vendor_spend_rows = (
        db.query(
            Vendor.id.label("vendor_id"),
            Vendor.company_name.label("vendor_name"),
            Vendor.category.label("category"),
            Vendor.vendor_type.label("vendor_type"),
            func.sum(PurchaseOrder.total_amount).label("total_spend"),
            func.count(PurchaseOrder.id).label("po_count")
        )
        .join(Vendor, PurchaseOrder.vendor_id == Vendor.id)
        .filter(PurchaseOrder.status.in_(["Approved", "Sent to Vendor", "Acknowledged",
                                          "Partially Received", "Received", "Closed"]))
        .group_by(Vendor.id, Vendor.company_name, Vendor.category, Vendor.vendor_type)
        .order_by(func.sum(PurchaseOrder.total_amount).desc())
        .limit(10)
        .all()
    )

    total_spend_all = sum(float(r.total_spend or 0) for r in vendor_spend_rows) or 1
    vendor_data = []
    for row in vendor_spend_rows:
        spend = float(row.total_spend or 0)
        vendor_data.append({
            "vendor_id"  : row.vendor_id,
            "vendor_name": row.vendor_name,
            "category"   : row.category,
            "vendor_type": row.vendor_type,
            "spend_inr"  : round(spend, 2),
            "po_count"   : row.po_count,
            "share_pct"  : round(spend / total_spend_all * 100, 1)
        })

    # ── 3. EBIT Margin Contribution ──────────────────────────────────────────
    # True EBIT savings = (RFQ Budget of finalized deals) - (Actual PO Commitment)
    # We filter to ONLY include RFQs that have an established PO to prevent inflation from open RFQs.
    closed_po_rfq_ids = db.query(PurchaseOrder.rfq_id).filter(
        PurchaseOrder.rfq_id.isnot(None),
        PurchaseOrder.status.in_(["Approved", "Sent to Vendor", "Acknowledged", 
                                  "Partially Received", "Received", "Closed"])
    ).subquery()

    rfq_total_budget = db.query(func.sum(RFQ.estimated_value))\
                           .filter(RFQ.id.in_(closed_po_rfq_ids))\
                           .scalar() or 0

    po_total_committed = db.query(func.sum(PurchaseOrder.total_amount))\
                             .filter(
                                 PurchaseOrder.status.in_(["Approved", "Sent to Vendor", "Acknowledged",
                                                           "Partially Received", "Received", "Closed"])
                             ).scalar() or 0

    ebit_savings    = max(0, round(float(rfq_total_budget) - float(po_total_committed), 2))
    ebit_margin_pct = round((ebit_savings / float(rfq_total_budget) * 100), 2) if rfq_total_budget > 0 else 0

    # Total overall spend
    overall_actual = sum(float(r.actual_spend or 0) for r in category_rows)
    overall_planned = sum(c["planned_inr"] for c in category_data)

    return {
        "category_spend"  : category_data,
        "vendor_allocation": vendor_data,
        "ebit": {
            "total_budget_inr"      : round(float(rfq_total_budget), 2),
            "total_committed_inr"   : round(float(po_total_committed), 2),
            "ebit_savings_inr"      : ebit_savings,
            "ebit_margin_pct"       : ebit_margin_pct,
            "label"                 : "Direct EBIT Addition (Procurement Savings)"
        },
        "summary": {
            "total_planned_inr": round(overall_planned, 2),
            "total_actual_inr" : round(overall_actual, 2),
            "overall_utilisation_pct": round((overall_actual / overall_planned * 100), 1) if overall_planned > 0 else 0
        }
    }
