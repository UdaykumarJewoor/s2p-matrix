# services/invoice_matcher.py
# BR-S2P-10: 3-Way Match Engine (PO ↔ GRN ↔ Invoice)
# Standalone service — reusable from router or pipeline
# Matrix Comsec Pvt. Ltd.

from sqlalchemy.orm import Session
from app.models.invoice import Invoice, GRN
from app.models.purchase_order import PurchaseOrder
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

AMOUNT_TOLERANCE_PCT = 2.0   # 2% tolerance on amount variance


def run_three_way_match(invoice_id: int, db: Session) -> dict:
    """
    Core 3-Way Match: validates Invoice against PO and GRN.

    Checks performed:
      1. PO exists and is linked
      2. Vendor on invoice matches PO vendor
      3. Invoice amount within 2% tolerance of PO amount
      4. GRN (Goods Receipt) exists and is accepted
      5. No duplicate invoice detected

    Updates invoice match_status and match_notes in DB.

    Returns:
        dict with match_status, issues, checks, and recommendation
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return {"error": f"Invoice {invoice_id} not found", "match_status": "Exception"}

    checks = []
    issues = []
    passed = 0
    total  = 5

    # ── Check 1: Duplicate Detection ────────────────────────────
    dup_count = db.query(Invoice).filter(
        Invoice.invoice_number == invoice.invoice_number,
        Invoice.vendor_id      == invoice.vendor_id,
        Invoice.id             != invoice_id
    ).count()

    if dup_count > 0:
        issues.append(f"⚠️ Duplicate invoice detected — {dup_count} matching record(s) found")
        checks.append({"check": "Duplicate Detection", "result": "❌ FAIL",
                       "detail": f"{dup_count} potential duplicate(s)"})
        invoice.is_duplicate = True
    else:
        passed += 1
        checks.append({"check": "Duplicate Detection", "result": "✅ PASS",
                       "detail": "No duplicates found"})

    # ── Check 2: PO Linkage ──────────────────────────────────────
    po = None
    if not invoice.po_id:
        issues.append("❌ No Purchase Order linked to this invoice")
        checks.append({"check": "PO Linkage", "result": "❌ FAIL",
                       "detail": "Invoice has no PO reference"})
    else:
        po = db.query(PurchaseOrder).filter(PurchaseOrder.id == invoice.po_id).first()
        if not po:
            issues.append("❌ Linked PO not found in system")
            checks.append({"check": "PO Linkage", "result": "❌ FAIL",
                           "detail": f"PO ID {invoice.po_id} missing"})
        else:
            passed += 1
            checks.append({"check": "PO Linkage", "result": "✅ PASS",
                           "detail": f"Linked to {po.po_number}"})

    # ── Check 3: Vendor Match ────────────────────────────────────
    if po:
        if po.vendor_id != invoice.vendor_id:
            issues.append(
                f"❌ Vendor mismatch — Invoice vendor_id={invoice.vendor_id}, "
                f"PO vendor_id={po.vendor_id}"
            )
            checks.append({"check": "Vendor Match", "result": "❌ FAIL",
                           "detail": "Invoice vendor ≠ PO vendor"})
        else:
            passed += 1
            checks.append({"check": "Vendor Match", "result": "✅ PASS",
                           "detail": "Vendor matches across PO and Invoice"})
    else:
        checks.append({"check": "Vendor Match", "result": "⏭️ SKIPPED",
                       "detail": "No PO to compare against"})

    # ── Check 4: Amount Tolerance ─────────────────────────────────
    if po:
        po_amount  = float(po.total_amount)
        inv_amount = float(invoice.total_amount)
        tolerance  = po_amount * (AMOUNT_TOLERANCE_PCT / 100)
        diff       = abs(inv_amount - po_amount)

        if diff <= tolerance:
            passed += 1
            checks.append({
                "check" : "Amount Tolerance",
                "result": "✅ PASS",
                "detail": (
                    f"PO=₹{po_amount:,.2f}, Invoice=₹{inv_amount:,.2f}, "
                    f"Diff=₹{diff:,.2f} (within {AMOUNT_TOLERANCE_PCT}% tolerance)"
                )
            })
        else:
            pct_diff = round((diff / po_amount) * 100, 2)
            issue_txt = (
                f"❌ Amount mismatch — PO=₹{po_amount:,.2f}, "
                f"Invoice=₹{inv_amount:,.2f}, Diff=₹{diff:,.2f} ({pct_diff}%)"
            )
            issues.append(issue_txt)
            checks.append({
                "check" : "Amount Tolerance",
                "result": "❌ FAIL",
                "detail": issue_txt
            })
    else:
        checks.append({"check": "Amount Tolerance", "result": "⏭️ SKIPPED",
                       "detail": "No PO to compare against"})

    # ── Check 5: GRN Confirmation & Item Verification ─────────────────────
    if invoice.grn_id:
        grn = db.query(GRN).filter(GRN.id == invoice.grn_id).first()
        if grn:
            # Check Quality Status First
            if grn.quality_status == "Rejected":
                issues.append(f"❌ GRN {grn.grn_number} rejected — goods not accepted")
                checks.append({"check": "GRN Quality", "result": "❌ FAIL", "detail": "Quality status: Rejected"})
            else:
                passed += 1
                checks.append({"check": "GRN Status", "result": "✅ PASS", "detail": f"GRN {grn.grn_number} is {grn.quality_status}"})

            # Check Item Quantities (The High-Fidelity Logic)
            from app.models.invoice import InvoiceItem
            inv_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).all()
            
            for it in inv_items:
                # Find corresponding PO item
                from app.models.purchase_order import POItem
                po_item = db.query(POItem).filter(POItem.id == it.po_item_id).first()
                if po_item:
                    if float(it.billed_qty) > float(po_item.quantity):
                        issues.append(f"❌ QUANTITY EXCEPTION on '{it.description}': Billed {it.billed_qty}, but only {po_item.quantity} were ordered.")
                        checks.append({"check": f"Line Item: {it.description[:20]}...", "result": "❌ FAIL", "detail": f"Billed {it.billed_qty} vs Ordered {po_item.quantity}"})
                    else:
                        checks.append({"check": f"Line Item: {it.description[:20]}...", "result": "✅ PASS", "detail": f"Qty {it.billed_qty} Matches"})
        else:
            issues.append("⚠️ GRN linked but not found in DB")
    else:
        issue_txt = "⚠️ No GRN (Goods Receipt Note) linked — goods delivery unconfirmed"
        issues.append(issue_txt)
        checks.append({"check": "GRN Confirmation", "result": "⚠️ WARNING", "detail": issue_txt})

    # ── Determine Match Status ────────────────────────────────────
    critical_failures = [i for i in issues if i.startswith("❌")]
    warnings_only     = [i for i in issues if i.startswith("⚠️")]

    if not issues:
        match_status = "Matched"
        summary      = "✅ 3-way match PASSED — PO, GRN, and Invoice all verified"
        invoice.status = "Approved"
    elif not critical_failures and warnings_only:
        match_status = "Partial Match"
        summary      = f"⚠️ Partial match — {len(warnings_only)} warning(s), no critical failures"
    elif len(critical_failures) == 1 and passed >= 3:
        match_status = "Partial Match"
        summary      = f"⚠️ Partial match — 1 discrepancy: {critical_failures[0]}"
    else:
        match_status = "Mismatch"
        summary      = f"❌ Match FAILED — {len(critical_failures)} critical issue(s) detected"

    # ── Persist Result ─────────────────────────────────────────────
    invoice.match_status = match_status
    invoice.match_notes  = summary
    db.commit()

    recommendation = _get_payment_recommendation(match_status, issues)

    logger.info(
        f"3-Way Match invoice_id={invoice_id}: "
        f"{match_status} ({passed}/{total} checks passed)"
    )

    return {
        "invoice_id"       : invoice_id,
        "internal_ref"     : invoice.internal_ref,
        "invoice_number"   : invoice.invoice_number,
        "match_status"     : match_status,
        "checks_passed"    : passed,
        "checks_total"     : total,
        "checks"           : checks,
        "issues"           : issues,
        "summary"          : summary,
        "recommendation"   : recommendation,
        "evaluated_at"     : str(datetime.utcnow()),
        "tolerance_used_pct": AMOUNT_TOLERANCE_PCT
    }


def _get_payment_recommendation(match_status: str, issues: list) -> str:
    if match_status == "Matched":
        return "🟢 APPROVE PAYMENT — All checks passed"
    elif match_status == "Partial Match":
        return "🟡 CONDITIONAL APPROVAL — Review warnings before releasing payment"
    else:
        return "🔴 HOLD PAYMENT — Resolve critical discrepancies with vendor before processing"


def batch_match_invoices(invoice_ids: list, db: Session) -> list:
    """Run 3-way match for a batch of invoice IDs."""
    results = []
    for inv_id in invoice_ids:
        try:
            result = run_three_way_match(inv_id, db)
            results.append(result)
        except Exception as e:
            logger.error(f"Match failed for invoice {inv_id}: {e}")
            results.append({"invoice_id": inv_id, "error": str(e)})
    return results


def get_unmatched_invoices(db: Session) -> list:
    """Return all invoices that need matching (status = Pending or Mismatch)."""
    from app.models.invoice import Invoice
    invoices = db.query(Invoice).filter(
        Invoice.match_status.in_(["Pending", "Mismatch", "Exception"])
    ).all()
    return [
        {
            "invoice_id"    : inv.id,
            "internal_ref"  : inv.internal_ref,
            "invoice_number": inv.invoice_number,
            "vendor_id"     : inv.vendor_id,
            "total_amount"  : float(inv.total_amount),
            "match_status"  : inv.match_status,
            "po_id"         : inv.po_id,
            "grn_id"        : inv.grn_id,
        }
        for inv in invoices
    ]
