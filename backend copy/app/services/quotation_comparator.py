# services/quotation_comparator.py
# BR-S2P-04: Predictive ML Quotation Comparison & Vendor Selection Engine
# Matrix Comsec Pvt. Ltd.

from sqlalchemy.orm import Session
from app.models.quotation import Quotation
from app.models.vendor import Vendor
from app.services.ml_predictor import predict_supplier_risk
import logging

logger = logging.getLogger(__name__)

def compare_and_select(
    rfq_id  : int,
    db      : Session,
    strategy: str = "ml_predictive"
) -> dict:
    """
    Predictive ML Quotation Comparison Engine.

    Passes quotation features through the scikit-learn Random Forest model
    to predict fulfillment success probability. Marks the safest/highest probability
    quote as the winner (is_recommended = True).
    """
    quotes = db.query(Quotation).filter(Quotation.rfq_id == rfq_id).all()
    if not quotes:
        return {"error": f"No quotations found for RFQ {rfq_id}", "winner": None}

    # Gather benchmark values
    amounts       = [float(q.total_amount) for q in quotes]
    min_amount    = min(amounts)
    max_amount    = max(amounts)
    min_lead_time = min([q.delivery_days or 30 for q in quotes])

    results = []

    for q in quotes:
        vendor = db.query(Vendor).filter(Vendor.id == q.vendor_id).first()
        v_score = float(vendor.performance_score or 50.0) if vendor else 50.0
        
        oem_status = 1 if (vendor and vendor.oem_approved) else 0
        lead_time = q.delivery_days or 30
        price_val = float(q.total_amount)

        # Calculate price variance vs lowest benchmark
        # If min_amount is 100 and this is 120, variance is +20%
        price_variance = 0.0
        if min_amount > 0:
            price_variance = ((price_val - min_amount) / min_amount) * 100

        # Run ML Inference
        features = {
            "hist_delivery_score": v_score,
            "hist_quality_score": v_score, # We assume performance covers both for now
            "price_variance_pct": price_variance,
            "is_oem": oem_status,
            "proposed_lead_time": lead_time
        }
        
        ml_result = predict_supplier_risk(features)
        ai_score = ml_result["confidence_pct"]  # 0 to 100

        reasoning = _build_reasoning(q, vendor, ml_result, price_variance)

        results.append({
            "quotation_id"    : q.id,
            "quotation_number": q.quotation_number,
            "vendor_id"       : q.vendor_id,
            "vendor_name"     : vendor.company_name if vendor else "Unknown",
            "vendor_type"     : vendor.vendor_type if vendor else "Unknown",
            "oem_approved"    : vendor.oem_approved if vendor else False,
            "total_amount"    : float(q.total_amount),
            "delivery_days"   : q.delivery_days,
            "warranty_months" : q.warranty_months,
            "payment_terms"   : q.payment_terms,
            "price_score"     : max(0, round(100 - price_variance, 2)), 
            "delivery_score"  : round(100 * (min_lead_time / lead_time), 1) if lead_time > 0 else 100,
            "warranty_score"  : q.warranty_months, 
            "performance_score": v_score,
            "ai_score"        : ai_score,
            "reasoning"       : reasoning,
            "recommended"     : False
        })

    # Sort by ML Success Probability descending
    results.sort(key=lambda x: x["ai_score"], reverse=True)

    # Mark winner
    winner = None
    if results:
        top = results[0]
        top["recommended"] = True
        winner = top

        # Persist ML score & recommendation in DB
        winning_q = db.query(Quotation).filter(
            Quotation.id == top["quotation_id"]
        ).first()
        if winning_q:
            winning_q.ai_score         = top["ai_score"]
            winning_q.ai_recommendation = top["reasoning"]
            winning_q.is_recommended   = True
            winning_q.status           = "Under Evaluation"

        # Update scores for all quotes
        for r in results[1:]:
            q_obj = db.query(Quotation).filter(Quotation.id == r["quotation_id"]).first()
            if q_obj:
                q_obj.ai_score         = r["ai_score"]
                q_obj.ai_recommendation = r["reasoning"]
                q_obj.is_recommended   = False

        db.commit()

    savings_vs_worst = 0.0
    if len(results) > 1:
        worst_price  = max(r["total_amount"] for r in results)
        best_price   = winner["total_amount"] if winner else worst_price
        savings_vs_worst = round(worst_price - best_price, 2)

    logger.info(
        f"ML Quotation comparison for RFQ {rfq_id}: "
        f"{len(results)} quotes, ML Winner={winner['quotation_number'] if winner else None}"
    )

    return {
        "rfq_id"            : rfq_id,
        "strategy"          : "ML Predictive Risk",
        "weights_used"      : "RandomForest Inference",
        "total_quotes"      : len(results),
        "ranked"            : results,
        "winner"            : winner,
        "savings_vs_highest": savings_vs_worst,
        "price_range"       : {
            "lowest" : min_amount,
            "highest": max_amount,
            "spread_pct": round(((max_amount - min_amount) / min_amount) * 100, 1) if min_amount else 0
        }
    }


def _build_reasoning(q, vendor, ml_result, price_variance) -> str:
    """Build human-readable ML reasoning based on the Random Forest predictions."""
    lines = []
    prob = ml_result["success_probability"]

    if prob >= 0.80:
        lines.append("🤖 ML PREDICTION: LOW RISK (High Confidence)")
    elif prob >= 0.55:
        lines.append("🤖 ML PREDICTION: MEDIUM RISK (Proceed with caution)")
    else:
        lines.append("🤖 ML PREDICTION: HIGH RISK (Likely to fail/delay)")

    lines.append(f"Success Probability: {ml_result['confidence_pct']}%")

    if price_variance == 0:
        lines.append(f"💰 Most cost-effective bid in bucket")
    elif price_variance > 0:
        lines.append(f"💸 {round(price_variance, 1)}% more expensive than cheapest bid")

    if vendor:
        if vendor.oem_approved:
            lines.append(f"🛡️ OEM verified")
        lines.append(f"📊 Hist. Performance: {vendor.performance_score or 50.0}/100")

    return " | ".join(lines)
