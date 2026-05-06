# services/ai_discovery.py
# BR-S2P-01: AI Vendor Discovery & Qualification
# Pure rule-based logic — no numpy/sklearn needed

from sqlalchemy.orm import Session
from app.models.vendor import Vendor
from app.models.payment import VendorPerformance
from app.models.purchase_order import PurchaseOrder

def discover_vendors_for_category(
    category : str,
    db       : Session,
    min_score: float = 0.0,
    oem_only : bool  = False
) -> list:
    query = db.query(Vendor).filter(
        Vendor.status.in_(["Approved"]),
        Vendor.category.in_([category, "Both"])
    )
    if oem_only:
        query = query.filter(Vendor.oem_approved == True)

    vendors = query.all()
    if not vendors:
        return []

    results = []
    for v in vendors:
        score, reasons, flags = qualify_vendor(v, db)
        if score >= min_score:
            results.append({
                "vendor_id"        : v.id,
                "vendor_code"      : v.vendor_code,
                "company_name"     : v.company_name,
                "category"         : v.category,
                "vendor_type"      : v.vendor_type,
                "city"             : v.city,
                "oem_approved"     : v.oem_approved,
                "oem_brand"        : v.oem_brand,
                "gst_number"       : v.gst_number,
                "msme_registered"  : v.msme_registered,
                "performance_score": float(v.performance_score or 0),
                "ai_match_score"   : score,
                "qualification"    : reasons,
                "risk_flags"       : flags,
                "recommendation"   : get_recommendation(score, flags)
            })

    results.sort(key=lambda x: x["ai_match_score"], reverse=True)
    return results


def qualify_vendor(vendor: Vendor, db: Session) -> tuple:
    """
    Intelligent AI Discovery Logic:
    1. Historical Reliability Dominance (60%)
    2. Compliance & Verification (20%)
    3. Structural & Strategic Fit (20%)
    4. Confidence Multiplier (Penalty for lack of data)
    """
    reasons = []
    flags   = []
    
    # --- Pillar 1: Real-time Historical Performance (50 pts) ---
    perf_records = db.query(VendorPerformance).filter(VendorPerformance.vendor_id == vendor.id).all()
    history_count = len(perf_records)
    
    # Real-time Volume & Delivery calculation directly from live POs
    pos = db.query(PurchaseOrder).filter(PurchaseOrder.vendor_id == vendor.id).all()
    realtime_total_orders = len(pos)
    
    if realtime_total_orders > 0:
        delivered_pos = [po for po in pos if po.status in ["Received", "Closed"]]
        delivered_count = len(delivered_pos)
        realtime_delivery_rate = (delivered_count / realtime_total_orders) * 100
        
        # Fallback to historical quality/response if available, else assume neutral 80%
        avg_quality  = sum(float(p.quality_score or 0) for p in perf_records) / history_count if history_count > 0 else 80.0
        avg_response = sum(float(p.response_score or 0) for p in perf_records) / history_count if history_count > 0 else 80.0
        
        # Weighted History: 50% Real-time Delivery, 30% Quality, 20% Response
        raw_perf = (realtime_delivery_rate * 0.5) + (avg_quality * 0.3) + (avg_response * 0.2)
        
        # Penalize Risk Outliers
        if realtime_delivery_rate < 60:
            raw_perf -= 15
            flags.append(f"🚨 High Delivery Risk: Live on-time rate {realtime_delivery_rate:.1f}%")
        if avg_quality < 70:
            raw_perf -= 10
            flags.append(f"⚠️ Quality Concerns: Historical quality score {avg_quality:.1f}%")
            
        perf_score = (raw_perf / 100) * 50
        reasons.append(f"✅ Proven History: {realtime_delivery_rate:.1f}% delivery rate over {realtime_total_orders} live orders")
    else:
        # Day-Zero Neutral Start
        perf_score = 25  # Mid-score for unknown
        reasons.append("ℹ️ New Vendor: No live delivery history in system yet")

    # --- Pillar 2: Compliance Foundation (20 pts) ---
    compliance_score = 0
    if vendor.gst_number and vendor.pan_number:
        compliance_score += 20
        reasons.append("✅ Fully Verified: GST and PAN records confirmed")
    elif vendor.gst_number:
        compliance_score += 10
        flags.append("⚠️ Partial Compliance: Missing PAN record")
    else:
        flags.append("❌ Non-Compliant: Missing GST/PAN")

    # --- Pillar 3: Structural Fit (20 pts) ---
    struct_score = 0
    if vendor.vendor_type == "OEM":
        struct_score += 20
        reasons.append("✅ Strategic Fit: Direct OEM for maximum reliability")
    elif vendor.vendor_type == "Distributor":
        struct_score += 15
        if vendor.oem_approved:
            struct_score += 5
            reasons.append("✅ Strategic Fit: Authorised OEM Distributor")
        else:
            reasons.append("ℹ️ Distributor: No direct OEM letter found")
    else:
        struct_score += 5
        flags.append("⚠️ Type Risk: Trading entity — verify source authenticity")

    # Rule: Local Bonus (Max 10 pts)
    local_score = 0
    gujarat_cities = ["ahmedabad","surat","vadodara","rajkot","gandhinagar"]
    if vendor.city and vendor.city.lower() in gujarat_cities:
        local_score += 10
        reasons.append("✅ Local logistics bonus: Faster delivery transit")

    # --- Confidence Weighting (The Intelligence Factor) ---
    raw_final = perf_score + compliance_score + struct_score + local_score
    
    # Confidence Factor: 0.7 for new, scales to 1.0 with 5+ orders
    import math
    confidence = 0.7 + (0.3 * (1 - math.exp(-history_count / 2)))
    
    final_score = round(raw_final * confidence, 2)
    
    if final_score > 90:
        reasons.insert(0, "🌟 PREFERRED CHAMPION")
    elif final_score < 40:
        flags.append("⛔ HIGH RISK VENDOR")

    return min(final_score, 100.0), reasons, flags

def get_recommendation(score: float, flags: list) -> str:
    critical = [f for f in flags if "🚨" in f or "❌" in f or "⛔" in f]
    if score >= 85 and not critical:
        return "🟢 TOP PERFORMER (Verified Legend)"
    elif score >= 70 and not critical:
        return "🟡 RELIABLE (Highly Recommended)"
    elif score >= 50:
        return "🟠 CONDITIONAL (New/Limited History)"
    else:
        return "🔴 NOT RECOMMENDED (Risk Detected)"


def get_market_benchmark(category: str, db: Session) -> dict:
    vendors = db.query(Vendor).filter(
        Vendor.category.in_([category, "Both"]),
        Vendor.status == "Approved"
    ).all()

    if not vendors:
        return {"message": "No benchmark data available"}

    scores = [float(v.performance_score or 0) for v in vendors]

    # Pure Python stats — no numpy needed
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    top_score = round(max(scores), 2) if scores else 0
    low_score = round(min(scores), 2) if scores else 0

    return {
        "category"    : category,
        "total_vendors": len(vendors),
        "avg_score"   : avg_score,
        "top_score"   : top_score,
        "low_score"   : low_score,
        "oem_vendors" : sum(1 for v in vendors if v.oem_approved),
        "msme_vendors": sum(1 for v in vendors if v.msme_registered),
    }