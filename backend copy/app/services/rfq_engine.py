# services/rfq_engine.py
# BR-S2P-03 + BR-S2P-04: RFQ Automation Engine
# Orchestrates: RFQ → AI Discovery → Auto-Quotation → Compare → PO
# Matrix Comsec Pvt. Ltd. — Security Systems Procurement

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.vendor import Vendor
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.services.ai_discovery import discover_vendors_for_category
from app.services.quotation_comparator import compare_and_select
import random
import logging

logger = logging.getLogger(__name__)

# ── Realistic base prices for Matrix Comsec product categories ──────────────
PRODUCT_BASE_PRICES = {
    # CCTV & Video Surveillance
    "IP Camera 2MP":               4500,
    "IP Camera 4MP":               7500,
    "IP Camera 8MP 4K":           14000,
    "PTZ Camera":                  28000,
    "Dome Camera 2MP":             3800,
    "Bullet Camera 4MP":           6200,
    "Fisheye 360 Camera":          12500,
    "Thermal Camera":              85000,
    "NVR 8 Channel":               18000,
    "NVR 16 Channel":              32000,
    "NVR 32 Channel":              58000,
    "DVR 8 Channel":               8500,
    "Hard Disk 4TB Surveillance":  7800,
    "Hard Disk 8TB Surveillance":  14500,
    "Video Management Software":   45000,
    # Access Control
    "Biometric Access Controller": 12000,
    "RFID Card Reader":            2800,
    "Proximity Card":               85,
    "Access Control Panel":        18500,
    "Face Recognition Terminal":   35000,
    "Electric Door Lock":          4500,
    "Magnetic Lock 600lb":         3200,
    "Exit Button":                  450,
    "Turnstile Flap Barrier":      95000,
    "Tripod Turnstile":            42000,
    # Intrusion Detection
    "PIR Motion Sensor":           1200,
    "Dual Tech Detector":          2800,
    "Glass Break Detector":        1800,
    "Magnetic Door Contact":        380,
    "Alarm Panel 8 Zone":          8500,
    "Alarm Panel 32 Zone":         22000,
    "Siren Outdoor":               1600,
    "Beam Detector":               6500,
    # Fire Detection (Bosch)
    "Optical Smoke Detector":      1850,
    "Heat Detector":               1650,
    "CO Detector":                 3200,
    "Manual Call Point":            950,
    "Fire Alarm Panel 8 Zone":    15500,
    "Fire Alarm Panel 32 Zone":   42000,
    "Addressable Smoke Detector":  3800,
    "Sounder Strobe":              2200,
    # Networking & Infrastructure
    "PoE Switch 8 Port":           6800,
    "PoE Switch 16 Port":         14500,
    "Managed Switch 24 Port":     32000,
    "Cat6 Cable (305m Box)":       4200,
    "Fiber Optic Cable (500m)":   12500,
    "Patch Panel 24 Port":         3800,
    "Network Cabinet 12U":         8500,
    "UPS 1KVA":                    9800,
    "UPS 2KVA":                   18500,
    # Mechanical / Hardware
    "GI Pipe 1 inch (6m)":         450,
    "Cable Tray 2 inch":           185,
    "Junction Box IP66":            280,
    "Conduit 20mm (30m)":          380,
    "Wall Bracket Heavy Duty":      650,
    "Pole Mount Bracket":          1200,
    "Cable Gland M20":              45,
    "Earthing Wire (100m)":        2800,
}

PAYMENT_TERMS_OPTIONS = [
    "30 days net", "45 days net", "60 days net",
    "30% advance, 70% on delivery",
    "50% advance, 50% on delivery",
    "100% advance",
    "LC at sight",
]

def _generate_quotation_number(db: Session) -> str:
    year  = datetime.now().year
    count = db.query(func.count(Quotation.id)).scalar()
    return f"QUO-{year}-{str(count + 1).zfill(4)}"

def _generate_po_number(db: Session) -> str:
    year  = datetime.now().year
    count = db.query(func.count(PurchaseOrder.id)).scalar()
    return f"PO-{year}-{str(count + 1).zfill(4)}"

def _simulate_vendor_price(base_price: float, vendor_score: float,
                            vendor_type: str, oem_approved: bool) -> float:
    """
    Simulate realistic pricing variation based on vendor profile.
    - OEMs: tightest pricing, closest to base
    - Distributors: +5% to +15%
    - Traders: +10% to +25%
    - Higher-scored vendors tend to price more competitively
    """
    if vendor_type == "OEM" and oem_approved:
        variation = random.uniform(-0.03, 0.08)
    elif vendor_type == "Distributor":
        variation = random.uniform(0.05, 0.18)
    elif vendor_type == "Trader":
        variation = random.uniform(0.10, 0.28)
    else:
        variation = random.uniform(0.02, 0.15)

    # Better-scored vendors price slightly more competitively
    score_factor = (100 - float(vendor_score)) / 1000
    variation    = max(-0.05, variation - score_factor)

    price = round(base_price * (1 + variation), 2)
    return max(price, base_price * 0.80)   # floor at 80% of base

def _get_delivery_days(vendor_type: str, city: str) -> int:
    """Simulate delivery days based on vendor type and location."""
    gujarat_cities = {"ahmedabad", "surat", "vadodara", "rajkot",
                      "gandhinagar", "anand", "bharuch", "mehsana"}
    is_local = city and city.lower() in gujarat_cities

    base = {"OEM": 21, "Distributor": 14, "Trader": 10, "Service": 30}
    days = base.get(vendor_type, 15)
    if is_local:
        days = max(3, days - 5)
    return days + random.randint(-3, 5)

def generate_quotations_for_rfq(
    rfq_id: int,
    vendor_list: list,
    db: Session,
    top_n: int = 7
) -> list:
    """
    Stage 3: Auto-generate simulated quotations for top-N vendors.
    Returns list of created quotation dicts.
    """
    rfq   = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise ValueError(f"RFQ {rfq_id} not found")

    items = db.query(RFQItem).filter(RFQItem.rfq_id == rfq_id).all()
    if not items:
        raise ValueError(f"RFQ {rfq_id} has no line items")

    selected_vendors = vendor_list[:top_n]
    created_quotes   = []

    for vdata in selected_vendors:
        vendor = db.query(Vendor).filter(Vendor.id == vdata["vendor_id"]).first()
        if not vendor:
            continue

        # Check if quotation already exists for this RFQ + Vendor
        existing = db.query(Quotation).filter(
            Quotation.rfq_id    == rfq_id,
            Quotation.vendor_id == vendor.id
        ).first()
        if existing:
            created_quotes.append({
                "quotation_id"    : existing.id,
                "quotation_number": existing.quotation_number,
                "vendor_id"       : vendor.id,
                "vendor_name"     : vendor.company_name,
                "total_amount"    : float(existing.total_amount),
                "status"          : "already_exists"
            })
            continue

        # Simulate line item pricing
        subtotal   = 0.0
        tax_amount = 0.0
        q_items    = []

        for item in items:
            # Look up base price or estimate from description
            base_key   = next(
                (k for k in PRODUCT_BASE_PRICES
                 if k.lower() in (item.description or "").lower()),
                None
            )
            base_price = PRODUCT_BASE_PRICES.get(base_key, 5000.0)
            unit_price = _simulate_vendor_price(
                base_price,
                float(vendor.performance_score or 50),
                vendor.vendor_type or "Distributor",
                vendor.oem_approved
            )
            qty        = float(item.quantity)
            tax_pct    = 18.0
            line_sub   = qty * unit_price
            line_tax   = line_sub * (tax_pct / 100)
            subtotal  += line_sub
            tax_amount += line_tax
            q_items.append({
                "rfq_item_id": item.id,
                "description": item.description,
                "quantity"   : qty,
                "unit_price" : unit_price,
                "tax_percent": tax_pct,
                "total_price": line_sub + line_tax
            })

        total_amount  = round(subtotal + tax_amount, 2)
        delivery_days = _get_delivery_days(
            vendor.vendor_type or "Distributor", vendor.city or ""
        )
        warranty_months = 12 if vendor.oem_approved else (6 if vendor.vendor_type == "Distributor" else 3)
        payment_terms   = random.choice(PAYMENT_TERMS_OPTIONS)
        valid_until     = date.today() + timedelta(days=30)

        quotation = Quotation(
            quotation_number = _generate_quotation_number(db),
            rfq_id           = rfq_id,
            vendor_id        = vendor.id,
            valid_until      = valid_until,
            payment_terms    = payment_terms,
            delivery_days    = delivery_days,
            warranty_months  = warranty_months,
            subtotal         = round(subtotal, 2),
            tax_amount       = round(tax_amount, 2),
            total_amount     = total_amount,
            status           = "Received",
            notes            = f"Auto-generated quotation via AI pipeline — vendor score: {vdata.get('ai_match_score', 0)}"
        )
        db.add(quotation)
        db.flush()

        for qi in q_items:
            db.add(QuotationItem(
                quotation_id = quotation.id,
                rfq_item_id  = qi["rfq_item_id"],
                description  = qi["description"],
                quantity     = qi["quantity"],
                unit_price   = qi["unit_price"],
                tax_percent  = qi["tax_percent"],
                total_price  = qi["total_price"]
            ))

        # Mark vendor as responded in rfq_vendors
        rv = db.query(RFQVendor).filter(
            RFQVendor.rfq_id    == rfq_id,
            RFQVendor.vendor_id == vendor.id
        ).first()
        if rv:
            rv.response_status = "Responded"

        db.flush()
        created_quotes.append({
            "quotation_id"    : quotation.id,
            "quotation_number": quotation.quotation_number,
            "vendor_id"       : vendor.id,
            "vendor_name"     : vendor.company_name,
            "total_amount"    : total_amount,
            "delivery_days"   : delivery_days,
            "warranty_months" : warranty_months,
            "payment_terms"   : payment_terms,
            "status"          : "created"
        })

    db.commit()
    logger.info(f"Generated {len(created_quotes)} quotations for RFQ-{rfq_id}")
    return created_quotes


def create_po_from_quotation(
    quotation_id: int,
    db: Session,
    created_by: str = "AI-Pipeline"
) -> dict:
    """
    Stage 5: Auto-create Purchase Order from winning quotation.
    """
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise ValueError(f"Quotation {quotation_id} not found")

    # Mark this quotation as selected, others as rejected
    rfq_quotes = db.query(Quotation).filter(Quotation.rfq_id == q.rfq_id).all()
    for other in rfq_quotes:
        if other.id == quotation_id:
            other.status         = "Selected"
            other.is_recommended = True
        else:
            other.status = "Rejected"

    delivery_date = date.today() + timedelta(days=q.delivery_days or 14)
    items         = q.items

    subtotal   = float(q.subtotal)
    tax_amount = float(q.tax_amount)
    total      = float(q.total_amount)

    po = PurchaseOrder(
        po_number        = _generate_po_number(db),
        vendor_id        = q.vendor_id,
        quotation_id     = quotation_id,
        rfq_id           = q.rfq_id,
        po_date          = date.today(),
        delivery_date    = delivery_date,
        subtotal         = subtotal,
        tax_amount       = tax_amount,
        total_amount     = total,
        payment_terms    = q.payment_terms,
        delivery_address = "Matrix Comsec Pvt. Ltd., Gujarat, India",
        created_by       = created_by,
        status           = "Approved",
        l1_approver      = "AI-System",
        l1_approved_at   = datetime.utcnow(),
        l2_approver      = "Bhavesh",
        l2_approved_at   = datetime.utcnow(),
        notes            = f"Auto-generated from quotation {q.quotation_number} via AI pipeline"
    )
    db.add(po)
    db.flush()

    for qi in items:
        db.add(POItem(
            po_id       = po.id,
            description = qi.description,
            quantity    = float(qi.quantity),
            unit        = "PCS",
            unit_price  = float(qi.unit_price),
            tax_percent = float(qi.tax_percent),
            total_price = float(qi.total_price)
        ))

    # Update RFQ status
    rfq = db.query(RFQ).filter(RFQ.id == q.rfq_id).first()
    if rfq:
        rfq.status = "Closed"

    db.commit()
    db.refresh(po)

    logger.info(f"Created PO {po.po_number} from quotation {q.quotation_number}")
    return {
        "po_id"          : po.id,
        "po_number"      : po.po_number,
        "vendor_id"      : po.vendor_id,
        "total_amount"   : float(po.total_amount),
        "delivery_date"  : str(po.delivery_date),
        "status"         : po.status,
        "payment_terms"  : po.payment_terms,
        "quotation_number": q.quotation_number
    }


def run_rfq_pipeline(rfq_id: int, db: Session,
                     strategy: str = "best_value",
                     top_vendors: int = 7) -> dict:
    """
    MASTER FUNCTION — State-Aware S2P Pipeline for one RFQ.
    Reads the RFQ's current stage first. Skips all already-completed stages.
    Safe to call multiple times — will never re-execute completed stages.

    Stages:
      1. Load & validate RFQ
      2. AI Vendor Discovery (category-based)
      3. Auto-generate quotations (simulated pricing)
      4. AI Quotation Comparison & vendor selection
      5. Auto-create PO from winning quotation
    """
    from app.services.rfq_stage_engine import get_rfq_current_stage, advance_rfq_stage

    pipeline_start = datetime.utcnow()
    audit          = {
        "pipeline_id"    : f"PIPE-{rfq_id}-{int(pipeline_start.timestamp())}",
        "rfq_id"         : rfq_id,
        "started_at"     : str(pipeline_start),
        "strategy"       : strategy,
        "stages"         : {}
    }

    # ── Load RFQ ────────────────────────────────────────────────
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise ValueError(f"RFQ {rfq_id} not found in database")

    # Detect real current stage from DB facts
    detected_stage = get_rfq_current_stage(rfq_id, db)
    audit["detected_stage_on_entry"] = detected_stage

    # ── STAGE 1: Load RFQ ───────────────────────────────────────
    t0    = datetime.utcnow()
    items = db.query(RFQItem).filter(RFQItem.rfq_id == rfq_id).all()
    audit["stages"]["stage_1_rfq"] = {
        "status"         : "✅ Completed",
        "duration_ms"    : int((datetime.utcnow() - t0).total_seconds() * 1000),
        "rfq_number"     : rfq.rfq_number,
        "title"          : rfq.title,
        "current_stage"  : detected_stage,
        "items_count"    : len(items),
        "estimated_value": float(rfq.estimated_value or 0)
    }
    advance_rfq_stage(rfq_id, 1, db)
    logger.info(f"Stage 1 complete: RFQ {rfq.rfq_number} (detected stage={detected_stage})")

    # ── STAGE 2: AI Vendor Discovery ────────────────────────────
    t0 = datetime.utcnow()
    if detected_stage >= 2:
        # Already done — report existing, skip
        rv_count = db.query(RFQVendor).filter(RFQVendor.rfq_id == rfq_id).count()
        audit["stages"]["stage_2_discovery"] = {
            "status"          : "⏩ Skipped (already completed)",
            "duration_ms"     : 0,
            "total_discovered": rv_count,
            "selected_for_rfq": rv_count,
            "top_vendors"     : []
        }
        top_vendors_list = [{"vendor_id": rv.vendor_id, "company_name": "existing",
                              "ai_match_score": 0, "recommendation": "existing",
                              "oem_approved": False}
                            for rv in db.query(RFQVendor).filter(RFQVendor.rfq_id == rfq_id).all()]
    else:
        # Execute Stage 2
        category = "Electronic"
        if rfq.category_id:
            from sqlalchemy import text as sql_text
            row = db.execute(
                sql_text("SELECT parent_category FROM commodity_categories WHERE id = :cid"),
                {"cid": rfq.category_id}
            ).fetchone()
            if row:
                cat_val = row[0]
                if cat_val == "Mechanical":
                    category = "Mechanical"
                elif cat_val == "Service":
                    category = "Both"

        discovered       = discover_vendors_for_category(category=category, db=db, min_score=30.0, oem_only=False)
        top_vendors_list = discovered[:top_vendors]

        for vd in top_vendors_list:
            exists = db.query(RFQVendor).filter(
                RFQVendor.rfq_id == rfq_id, RFQVendor.vendor_id == vd["vendor_id"]
            ).first()
            if not exists:
                db.add(RFQVendor(rfq_id=rfq_id, vendor_id=vd["vendor_id"],
                                 sent_at=datetime.utcnow(), response_status="Pending"))

        rfq.status = "Sent"
        db.commit()
        advance_rfq_stage(rfq_id, 2, db)

        audit["stages"]["stage_2_discovery"] = {
            "status"          : "✅ Completed",
            "duration_ms"     : int((datetime.utcnow() - t0).total_seconds() * 1000),
            "category"        : category,
            "total_discovered": len(discovered),
            "selected_for_rfq": len(top_vendors_list),
            "top_vendors"     : [
                {"vendor_id": v["vendor_id"], "company_name": v["company_name"],
                 "ai_match_score": v["ai_match_score"], "recommendation": v["recommendation"],
                 "oem_approved": v["oem_approved"]}
                for v in top_vendors_list
            ]
        }
        logger.info(f"Stage 2 complete: Discovered {len(discovered)} vendors")

        if not top_vendors_list:
            audit["stages"]["stage_2_discovery"]["status"] = "⚠️ No vendors found"
            audit["completed_at"] = str(datetime.utcnow())
            audit["result"]       = "STOPPED — No vendors available for this category"
            return audit

    # ── STAGE 3: Auto-generate Quotations ───────────────────────
    t0 = datetime.utcnow()
    if detected_stage >= 3:
        existing_quotes = db.query(Quotation).filter(Quotation.rfq_id == rfq_id).all()
        audit["stages"]["stage_3_quotations"] = {
            "status"           : "⏩ Skipped (already completed)",
            "duration_ms"      : 0,
            "quotations_count" : len(existing_quotes),
            "quotations"       : [{"quotation_number": q.quotation_number,
                                   "total_amount": float(q.total_amount)} for q in existing_quotes]
        }
    else:
        quotations_created = generate_quotations_for_rfq(
            rfq_id=rfq_id, vendor_list=top_vendors_list, db=db, top_n=top_vendors
        )
        rfq.status = "Responses Received"
        db.commit()
        advance_rfq_stage(rfq_id, 3, db)

        audit["stages"]["stage_3_quotations"] = {
            "status"           : "✅ Completed",
            "duration_ms"      : int((datetime.utcnow() - t0).total_seconds() * 1000),
            "quotations_count" : len(quotations_created),
            "quotations"       : quotations_created
        }
        logger.info(f"Stage 3 complete: Generated {len(quotations_created)} quotations")

    # ── STAGE 4: AI Comparison & Vendor Selection ────────────────
    t0 = datetime.utcnow()
    if detected_stage >= 4:
        existing_winner = db.query(Quotation).filter(
            Quotation.rfq_id == rfq_id, Quotation.is_recommended == True
        ).first()
        winner = {"quotation_id": existing_winner.id,
                  "vendor_name": f"Vendor #{existing_winner.vendor_id}",
                  "total_amount": float(existing_winner.total_amount)} if existing_winner else None
        audit["stages"]["stage_4_comparison"] = {
            "status"     : "⏩ Skipped (already completed)",
            "duration_ms": 0,
            "strategy"   : strategy,
            "winner"     : winner
        }
    else:
        rfq.status = "Evaluation"
        db.commit()
        comparison_result = compare_and_select(rfq_id=rfq_id, db=db, strategy=strategy)
        winner            = comparison_result.get("winner")
        advance_rfq_stage(rfq_id, 4, db)

        audit["stages"]["stage_4_comparison"] = {
            "status"     : "✅ Completed",
            "duration_ms": int((datetime.utcnow() - t0).total_seconds() * 1000),
            "strategy"   : strategy,
            "ranked"     : comparison_result.get("ranked", []),
            "winner"     : winner
        }
        logger.info(f"Stage 4 complete: Winner → quotation_id={winner.get('quotation_id') if winner else None}")

        if not winner:
            audit["completed_at"] = str(datetime.utcnow())
            audit["result"]       = "STOPPED — Could not determine winning quotation"
            return audit

    # ── STAGE 5: Auto-create PO ──────────────────────────────────
    t0 = datetime.utcnow()
    if detected_stage >= 5:
        existing_po = db.query(PurchaseOrder).filter(PurchaseOrder.rfq_id == rfq_id).first()
        po_result = {
            "po_id"       : existing_po.id,
            "po_number"   : existing_po.po_number,
            "total_amount": float(existing_po.total_amount),
            "delivery_date": str(existing_po.delivery_date),
            "status"      : existing_po.status
        }
        audit["stages"]["stage_5_po"] = {
            "status"     : "⏩ Skipped (PO already exists)",
            "duration_ms": 0,
            "po"         : po_result
        }
        logger.info(f"Stage 5 skipped: PO {existing_po.po_number} already exists")
    else:
        if not winner:
            audit["completed_at"] = str(datetime.utcnow())
            audit["result"]       = "STOPPED — No winner to create PO from"
            return audit
        po_result = create_po_from_quotation(
            quotation_id=winner["quotation_id"], db=db, created_by="AI-Pipeline"
        )
        advance_rfq_stage(rfq_id, 5, db)

        audit["stages"]["stage_5_po"] = {
            "status"     : "✅ Completed",
            "duration_ms": int((datetime.utcnow() - t0).total_seconds() * 1000),
            "po"         : po_result
        }
        logger.info(f"Stage 5 complete: PO {po_result['po_number']} created")

    audit["completed_at"]      = str(datetime.utcnow())
    audit["total_duration_ms"] = int((datetime.utcnow() - pipeline_start).total_seconds() * 1000)
    audit["result"]            = "✅ PIPELINE COMPLETE — Stages 1-5 done (PO exists)"
    audit["summary"] = {
        "rfq_number"          : rfq.rfq_number,
        "detected_stage"      : detected_stage,
        "po_number"           : po_result.get("po_number"),
        "po_id"               : po_result.get("po_id"),
        "po_total_inr"        : po_result.get("total_amount"),
        "delivery_date"       : po_result.get("delivery_date"),
        "next_step"           : "Run Complete PO (Stage 6-8)"
    }
    return audit

