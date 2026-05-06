# routers/invoices.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.invoice import Invoice, GRN, GRNItem, InvoiceItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.payment import Payment
from app.models.vendor import Vendor
from app.utils.audit import log_action
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

router = APIRouter()

class InvoiceCreate(BaseModel):
    invoice_number : str
    vendor_id      : int
    po_id          : Optional[int] = None
    grn_id         : Optional[int] = None
    invoice_date   : date
    due_date       : Optional[date] = None
    subtotal       : float
    tax_amount     : Optional[float] = 0.0
    total_amount   : float

class GRNItemIn(BaseModel):
    po_item_id    : int
    description   : str
    ordered_qty   : float
    received_qty  : float
    rejected_qty  : float = 0.0

class GRNCreate(BaseModel):
    po_id         : int
    vendor_id     : int
    received_date : date
    received_by   : Optional[str] = "warehouse"
    notes         : Optional[str] = None
    quality_status: Optional[str] = "Accepted"
    auto_settle   : Optional[bool] = False
    items           : List[GRNItemIn] = []
    # Base64 placeholder for simulation
    invoice_file_b64: Optional[str] = None
    payment_method  : Optional[str] = "NEFT"

class PaymentCreate(BaseModel):
    invoice_id     : int
    vendor_id      : int
    amount         : float
    payment_mode   : Optional[str] = "NEFT"
    payment_date   : date
    bank_reference : Optional[str] = None
    notes          : Optional[str] = None

class ReprocessInvoice(BaseModel):
    """Schema for reprocessing a GRN — update GRN data + re-match new invoice."""
    received_date    : date
    received_by      : Optional[str] = "Warehouse Admin"
    notes            : Optional[str] = None
    quality_status   : Optional[str] = "Accepted"
    items            : List[GRNItemIn] = []
    invoice_file_b64 : Optional[str] = None
    payment_method   : Optional[str] = "NEFT"
    auto_settle      : Optional[bool] = False

def generate_ref(prefix: str, db: Session, model) -> str:
    """
    Robust Reference Generator: Scans for actual MAX value to prevent 
    Integrity Errors and ID collisions.
    """
    year = datetime.now().year
    # Find the highest existing serial number for this year and prefix
    # We look for records starting with 'prefix-year-'
    base = f"{prefix}-{year}-"
    
    # Robust starting point: use MAX ID to prevent collisions after wipes
    max_id = db.query(func.max(model.id)).scalar() or 0
    seq = max_id + 1
    ref = f"{base}{str(seq).zfill(4)}"
    
    # While this ref exists, keep incrementing (Self-Healing Logic)
    # This prevents the 'Duplicate Entry' 500 errors.
    exists = True
    while exists:
        # Check for model-specific reference columns (Flexible Matching)
        attr_name = "internal_ref"
        if hasattr(model, "grn_number"):
            attr_name = "grn_number"
        elif hasattr(model, "invoice_number"):
            attr_name = "invoice_number"
        elif hasattr(model, "payment_ref"):
            attr_name = "payment_ref"
            
        chk = db.query(model).filter(getattr(model, attr_name) == ref).first()
        if not chk:
            exists = False
        else:
            seq += 1
            ref = f"{base}{str(seq).zfill(4)}"
            
    return ref

# ── INVOICE ROUTES ────────────────────────────────────────────

@router.get("/")
def get_invoices(match_status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if match_status:
        query = query.filter(Invoice.match_status == match_status)
    return {"invoices": query.order_by(Invoice.created_at.desc()).all()}

@router.post("/")
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_db)):
    # Duplicate check
    dup = db.query(Invoice).filter(
        Invoice.invoice_number == data.invoice_number,
        Invoice.vendor_id      == data.vendor_id
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"Duplicate invoice detected! Invoice {data.invoice_number} from this vendor already exists.")

    # ── BR-S2P-Match: Auto-link existing GRN if one was recorded before this Invoice
    grn_id = data.grn_id
    if not grn_id and data.po_id:
        existing_grn = db.query(GRN).filter(GRN.po_id == data.po_id).order_by(GRN.created_at.desc()).first()
        if existing_grn:
            grn_id = existing_grn.id

    internal_ref = generate_ref("INV", db, Invoice)
    invoice = Invoice(
        invoice_number = data.invoice_number,
        internal_ref   = internal_ref,
        vendor_id      = data.vendor_id,
        po_id          = data.po_id,
        grn_id         = grn_id,
        invoice_date   = data.invoice_date,
        due_date       = data.due_date,
        subtotal       = data.subtotal,
        tax_amount     = data.tax_amount,
        total_amount   = data.total_amount,
        is_duplicate   = False,
        status         = "Received",
        match_status   = "Pending"
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    log_action(
        table_name="invoices",
        record_id=invoice.id,
        action="CREATE",
        changed_by="system",
        old_values=None,
        new_values={"status": "Received", "match_status": "Pending", "total_amount": float(invoice.total_amount)},
        db=db
    )

    return {"message": "Invoice received", "invoice": invoice}

# POST 3-way match (BR-S2P-10)
@router.post("/{invoice_id}/match")
def three_way_match(invoice_id: int, db: Session = Depends(get_db)):
    """
    High-Integrity 3-Way Match Engine (PO vs GRN vs Invoice)
    Now performs Granular Line-Item Verification.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_match = invoice.match_status
    issues = []

    # 1. Verification: Header Level (PO & Vendor)
    if not invoice.po_id:
        issues.append("No PO linked — source of truth missing")
    else:
        po = db.query(PurchaseOrder).filter(PurchaseOrder.id == invoice.po_id).first()
        if not po:
            issues.append("Linked PO not found")
        elif po.vendor_id != invoice.vendor_id:
            issues.append("VENDOR MISMATCH: Invoice vendor does not match PO vendor")

    # 2. Verification: Receipt Check (GRN)
    if not invoice.grn_id:
        issues.append("No Receipt (GRN) found — cannot verify physical delivery")
    
    # 3. VERIFICATION: Granular Line-Item Audit (THE 'NO-LIES' CHECK)
    if invoice.grn_id and invoice.items:
        grn_items = db.query(GRNItem).filter(GRNItem.grn_id == invoice.grn_id).all()
        # Create a map of PO Item ID -> Accepted Quantity
        receipt_map = {item.po_item_id: float(item.accepted_qty) for item in grn_items}
        
        # Create a map for PO Item -> Agreed Unit Price
        po_price_map = {item.id: float(item.unit_price) for item in po.items} if po else {}
        
        for inv_item in invoice.items:
            accepted_qty = receipt_map.get(inv_item.po_item_id, 0)
            billed_qty   = float(inv_item.billed_qty)
            
            # Rule 3: Quantity Check
            if billed_qty > accepted_qty:
                issues.append(
                    f"QUANTITY EXCEPTION on '{inv_item.description}': "
                    f"Billed {billed_qty}, but only {accepted_qty} were accepted in GRN."
                )
                
            # Rule 4: Unit Pricing Check
            agreed_price = po_price_map.get(inv_item.po_item_id)
            if agreed_price is not None:
                billed_price = float(inv_item.unit_price)
                if abs(billed_price - agreed_price) > 0.5: # Strict tolerance
                    issues.append(
                        f"UNIT PRICE MISMATCH on '{inv_item.description}': "
                        f"Invoiced at ₹{billed_price}, but PO agreed price is ₹{agreed_price}."
                    )

    # 4. Verification: Financial Match
    if po:
        # Calculate expected total based on GRN accepted quantities (handles partial deliveries)
        expected_total = 0.0
        if invoice.grn_id and invoice.items:
            grn_items = db.query(GRNItem).filter(GRNItem.grn_id == invoice.grn_id).all()
            receipt_map = {item.po_item_id: float(item.accepted_qty) for item in grn_items}
            po_price_map = {item.id: float(item.unit_price) for item in po.items}
            po_tax_map = {item.id: float(item.tax_percent) for item in po.items}
            
            for item in po.items:
                accepted = receipt_map.get(item.id, 0)
                price = po_price_map.get(item.id, 0)
                tax = po_tax_map.get(item.id, 18.0)
                line_sub = accepted * price
                expected_total += line_sub * (1 + tax / 100)
        else:
            expected_total = float(po.total_amount)

        tolerance = 0.01  # 1% tolerance for minor rounding
        diff = abs(float(invoice.total_amount) - expected_total)
        if diff > (tolerance * expected_total) and diff > 10: # >10 INR absolute diff
            issues.append(f"FINANCIAL DISCREPANCY: Invoice Total (₹{invoice.total_amount}) "
                          f"does not match Expected Total (₹{round(expected_total, 2)}) based on GRN.")

    # 4. Final Status Determination
    if not issues:
        invoice.match_status = "Matched"
        invoice.match_notes  = "✅ All checks passed: Headers, Quantities, and Line-Items verified."
        invoice.status       = "Approved"
    else:
        invoice.match_status = "Mismatch"
        invoice.match_notes  = f"❌ Verification Failed: {'; '.join(issues)}"
        invoice.status       = "Under Review"

    db.commit()

    # Log results
    log_action(
        table_name="invoices",
        record_id=invoice_id,
        action="MATCH",
        changed_by="ai-matching-engine",
        old_values={"match_status": old_match},
        new_values={"match_status": invoice.match_status, "match_notes": invoice.match_notes},
        db=db
    )

    return {
        "status": "success",
        "match_status": invoice.match_status,
        "notes": invoice.match_notes,
        "exceptions_found": len(issues)
    }

# ── GRN ROUTES ────────────────────────────────────────────────

@router.get("/grn/")
def get_grns(db: Session = Depends(get_db)):
    return {"grns": db.query(GRN).order_by(GRN.created_at.desc()).all()}

@router.get("/grn/{grn_id}")
def get_grn_detail(grn_id: int, db: Session = Depends(get_db)):
    """Get a single GRN with its items and associated PO item details for pre-filling the reprocess form."""
    grn = db.query(GRN).filter(GRN.id == grn_id).first()
    if not grn:
        raise HTTPException(status_code=404, detail=f"GRN #{grn_id} not found.")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == grn.po_id).first()

    items = []
    for gi in grn.items:
        items.append({
            "id"          : gi.id,
            "po_item_id"  : gi.po_item_id,
            "description" : gi.description,
            "ordered_qty" : float(gi.ordered_qty or 0),
            "received_qty": float(gi.received_qty or 0),
            "accepted_qty": float(gi.accepted_qty or 0),
            "rejected_qty": float(gi.rejected_qty or 0),
        })

    return {
        "id"            : grn.id,
        "grn_number"    : grn.grn_number,
        "po_id"         : grn.po_id,
        "po_number"     : po.po_number if po else None,
        "vendor_id"     : grn.vendor_id,
        "received_date" : str(grn.received_date),
        "received_by"   : grn.received_by,
        "quality_status": grn.quality_status,
        "notes"         : grn.notes,
        "items"         : items
    }


@router.post("/reprocess-invoice/{grn_id}")
def reprocess_invoice(grn_id: int, data: ReprocessInvoice, db: Session = Depends(get_db)):
    """
    Full reprocess of a GRN: update receipt data (items, qty, quality)
    then re-upload the vendor invoice and re-run 3-way matching.
    """
    # 1. Find the existing GRN
    grn = db.query(GRN).filter(GRN.id == grn_id).first()
    if not grn:
        raise HTTPException(status_code=404, detail=f"GRN #{grn_id} not found.")

    # 2. Load the associated PO
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == grn.po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO associated with this GRN not found.")

    try:
        # ── STEP A: Update GRN core fields ──────────────────────────
        grn.received_date  = data.received_date
        grn.received_by    = data.received_by
        grn.notes          = data.notes

        # Auto-calculate quality from rejections if items provided
        if data.items:
            has_rejection = any(item.rejected_qty > 0 for item in data.items)
            all_rejected  = all(item.rejected_qty >= item.ordered_qty for item in data.items)
            if all_rejected:
                grn.quality_status = "Rejected"
            elif has_rejection:
                grn.quality_status = "Partially Accepted"
            else:
                grn.quality_status = data.quality_status or "Accepted"
        else:
            grn.quality_status = data.quality_status or "Accepted"

        # ── STEP B: Replace GRN line items ───────────────────────────
        if data.items:
            db.query(GRNItem).filter(GRNItem.grn_id == grn_id).delete()
            for item in data.items:
                db.add(GRNItem(
                    grn_id       = grn.id,
                    po_item_id   = item.po_item_id,
                    description  = item.description,
                    ordered_qty  = item.ordered_qty,
                    received_qty = item.received_qty,
                    accepted_qty = item.received_qty - item.rejected_qty,
                    rejected_qty = item.rejected_qty
                ))
        db.flush()

        # ── STEP C: If no invoice uploaded, just commit GRN update ──
        if not data.invoice_file_b64:
            db.commit()
            return {
                "status"     : "success",
                "match_status": "Pending",
                "message"    : "GRN updated. No invoice submitted — payment pipeline pending.",
                "grn_number" : grn.grn_number
            }

        # ── STEP D: Re-run invoice extraction ───────────────────────
        from app.services.invoice_processing import process_simulated_invoice

        # Prepare PO Items for the AI, dynamically scaling down to GRN received quantities
        grn_qty_map = {item.po_item_id: (float(item.received_qty) - float(item.rejected_qty)) for item in data.items}
        
        expected_total = 0.0
        po_items_data = []
        for it in po.items:
            acc_qty = grn_qty_map.get(it.id, 0)
            po_items_data.append({
                "id": it.id, "description": it.description, 
                "quantity": acc_qty,
                "unit_price": float(it.unit_price), "tax_percent": float(it.tax_percent)
            })
            expected_total += acc_qty * float(it.unit_price) * (1 + float(it.tax_percent) / 100)

        po_dict = {
            "po_number"   : po.po_number,
            "total_amount": expected_total,
            "items"       : po_items_data
        }
        extracted = process_simulated_invoice(data.invoice_file_b64, po_dict)

        # ── STEP E: Update or create the invoice record ──────────────
        existing_inv = db.query(Invoice).filter(Invoice.grn_id == grn_id).order_by(Invoice.id.desc()).first()

        if existing_inv:
            existing_inv.subtotal       = extracted["subtotal"]
            existing_inv.tax_amount     = extracted["tax_captured"]
            existing_inv.total_amount   = extracted["total_amount"]
            existing_inv.match_status   = "Pending"
            existing_inv.payment_status = "Unpaid"
            existing_inv.status         = "Received"
            existing_inv.match_notes    = None
            db.query(InvoiceItem).filter(InvoiceItem.invoice_id == existing_inv.id).delete()
            for ext_item in extracted.get("items", []):
                db.add(InvoiceItem(
                    invoice_id  = existing_inv.id,
                    po_item_id  = ext_item["po_item_id"],
                    description = ext_item["description"],
                    billed_qty  = ext_item["billed_qty"],
                    unit_price  = ext_item["unit_price"],
                    total_price = ext_item["total_price"]
                ))
            db.flush()
            auto_inv = existing_inv
        else:
            auto_inv = Invoice(
                invoice_number = f"INV-REPO-{grn.grn_number}",
                internal_ref   = generate_ref("INV", db, Invoice),
                vendor_id      = grn.vendor_id,
                po_id          = grn.po_id,
                grn_id         = grn.id,
                invoice_date   = data.received_date,
                subtotal       = extracted["subtotal"],
                tax_amount     = extracted["tax_captured"],
                total_amount   = extracted["total_amount"],
                match_status   = "Pending"
            )
            db.add(auto_inv)
            db.flush()
            for ext_item in extracted.get("items", []):
                db.add(InvoiceItem(
                    invoice_id  = auto_inv.id,
                    po_item_id  = ext_item["po_item_id"],
                    description = ext_item["description"],
                    billed_qty  = ext_item["billed_qty"],
                    unit_price  = ext_item["unit_price"],
                    total_price = ext_item["total_price"]
                ))
            db.flush()

        # ── STEP F: Wrong invoice gate ────────────────────────────────
        if extracted.get("is_mismatch"):
            auto_inv.match_status   = "Mismatch"
            auto_inv.match_notes    = "BLOCKED: " + extracted.get("mismatch_reason", "Invoice does not match PO.")
            auto_inv.status         = "Under Review"
            auto_inv.payment_status = "On Hold"
            grn.quality_status      = "GRN Payment Run: Failed"
            db.commit()
            return {"status": "mismatch", "match_status": "Mismatch",
                    "message": auto_inv.match_notes, "grn_number": grn.grn_number}

        # ── STEP G: GRN-Aware 3-Way Grand Total Check ───────────────────
        # The PDF extraction reliably gives us the grand total.
        # We compare it against: GRN accepted qty × PO agreed prices × (1 + tax).
        # This correctly handles partial deliveries and catches overcharging.
        issues = []

        grn_accepted = {gi.po_item_id: float(gi.accepted_qty or 0) for gi in grn.items}
        expected_total = sum(
            grn_accepted.get(po_item.id, 0)
            * float(po_item.unit_price)
            * (1 + float(po_item.tax_percent) / 100)
            for po_item in po.items
        )

        if abs(expected_total - float(extracted["total_amount"])) > 1.0:
            issues.append(
                f"Grand Total Mismatch: Expected ₹{expected_total:,.2f} "
                f"(GRN accepted qty × PO agreed prices incl. GST), "
                f"Invoice shows ₹{extracted['total_amount']:,.2f}."
            )

        if issues:
            grn.quality_status      = "GRN Payment Run: Failed"
            auto_inv.match_status   = "Mismatch"
            auto_inv.match_notes    = "FAILED: " + "; ".join(issues)
            auto_inv.status         = "Under Review"
            auto_inv.payment_status = "On Hold"
            db.commit()
            return {"status": "mismatch", "match_status": "Mismatch",
                    "message": auto_inv.match_notes, "grn_number": grn.grn_number}

        # ── STEP H: Match passed — approve ────────────────────────────
        grn.quality_status      = "Accepted"
        # ── BR-STATUS: Smart PO Status Update (Reprocess)
        total_ordered = sum(float(it.quantity) for it in po.items)
        total_accepted = db.query(func.sum(GRNItem.accepted_qty))\
            .join(GRN)\
            .filter(GRN.po_id == po.id)\
            .filter(GRN.quality_status == "Accepted")\
            .scalar() or 0.0
        
        if float(total_accepted) >= total_ordered:
            po.status = "Received"
        else:
            po.status = "Partially Received"
        auto_inv.match_status   = "Matched"
        auto_inv.match_notes    = "Reprocessed: 3-Way Match Verified."
        auto_inv.status         = "Approved"
        auto_inv.payment_status = "Unpaid"

        if data.auto_settle:
            pay = Payment(
                payment_ref  = generate_ref("PAY", db, Payment),
                invoice_id   = auto_inv.id,
                vendor_id    = grn.vendor_id,
                amount       = extracted["total_amount"],
                payment_mode = data.payment_method or "NEFT",
                payment_date = data.received_date,
                status       = "Processed",
                notes        = "Auto-Settlement via Reprocessed GRN"
            )
            db.add(pay)
            auto_inv.payment_status = "Paid"

        db.commit()
        return {
            "status"      : "success",
            "match_status": "Matched",
            "message"     : "GRN updated, invoice reprocessed and verified. 3-Way Match PASSED.",
            "grn_number"  : grn.grn_number
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reprocess Error: {str(e)}")


@router.post("/grn/")
def create_grn(data: GRNCreate, db: Session = Depends(get_db)):
    # ── BR-IDEMPOTENCY: Partial Delivery Gate
    # Allows a new receipt if the PO is not yet fully fulfilled across its GRNs.
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == data.po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found.")

    # Calculate total quantity ordered vs total accepted so far
    total_ordered = sum(float(it.quantity) for it in po.items)
    
    # Sum up all accepted quantities from previous successful GRNs
    total_accepted_so_far = db.query(func.sum(GRNItem.accepted_qty))\
        .join(GRN)\
        .filter(GRN.po_id == data.po_id)\
        .filter(GRN.quality_status != "GRN Payment Run: Failed")\
        .scalar() or 0.0
    
    if float(total_accepted_so_far) >= total_ordered:
        raise HTTPException(
            status_code=400, 
            detail=f"Fulfillment Error: PO#{po.po_number} has already been fully received and processed."
        )

    # GRN number logic
    grn_num = generate_ref("GRN", db, GRN)
    
    # ── BR-QUALITY: Check overall quality status based on rejections
    final_quality = "Accepted"
    if any(item.rejected_qty > 0 for item in data.items):
        final_quality = "Partially Accepted"
    
    grn = GRN(
        grn_number    = grn_num,
        po_id         = data.po_id,
        vendor_id     = data.vendor_id,
        received_date = data.received_date,
        received_by   = data.received_by,
        notes         = data.notes,
        quality_status= final_quality
    )
    db.add(grn)
    db.flush() # Get GRN ID
    
    # ── BR-CHECKLIST: Save Line Items from the Warehouse Verification
    for item in data.items:
        db.add(GRNItem(
            grn_id       = grn.id,
            po_item_id   = item.po_item_id,
            description  = item.description,
            ordered_qty  = item.ordered_qty,
            received_qty = item.received_qty,
            accepted_qty = item.received_qty - item.rejected_qty,
            rejected_qty = item.rejected_qty
        ))
    
    # ── BR-STATUS: Smart PO Status Update
    # Check if this new delivery fulfills the remaining balance
    current_grn_accepted = sum(float(item.received_qty) - float(item.rejected_qty) for item in data.items)
    new_total_accepted = float(total_accepted_so_far) + current_grn_accepted
    
    if new_total_accepted >= total_ordered:
        po.status = "Received"
    else:
        po.status = "Partially Received"
    
    db.commit()
    db.refresh(grn)

    # ── INTEGRATED INVOICE CAPTURE: Simulated AI Extraction Logic ──
    try:
        if data.invoice_file_b64 or data.auto_settle:
            from app.services.invoice_processing import process_simulated_invoice
            
            # Prepare PO Items for the 'AI' to read, scaling to GRN accepted quantities
            po_items_data = []
            expected_total = 0.0
            
            if po:
                grn_qty_map = {item.po_item_id: (float(item.received_qty) - float(item.rejected_qty)) for item in data.items}
                for it in po.items:
                    acc_qty = grn_qty_map.get(it.id, 0)
                    po_items_data.append({
                        "id": it.id, "description": it.description, 
                        "quantity": acc_qty, 
                        "unit_price": float(it.unit_price), "tax_percent": float(it.tax_percent)
                    })
                    expected_total += acc_qty * float(it.unit_price) * (1 + float(it.tax_percent) / 100)
                
            po_dict = {
                "po_number": po.po_number if po else "",
                "total_amount": expected_total, 
                "items": po_items_data
            }
            extracted = process_simulated_invoice(data.invoice_file_b64, po_dict)
            
            # 1. Create Invoice Header
            inv_num = f"INV-{grn.grn_number}"
            auto_inv = Invoice(
                invoice_number = inv_num,
                internal_ref   = generate_ref("INV", db, Invoice),
                vendor_id      = data.vendor_id,
                po_id          = data.po_id,
                grn_id         = grn.id,
                invoice_date   = data.received_date,
                subtotal       = extracted["subtotal"],
                tax_amount     = extracted["tax_captured"],
                total_amount   = extracted["total_amount"],
                match_status   = "Pending"
            )
            db.add(auto_inv)
            db.flush() # Get Invoice ID

            # 2. Create Invoice Line Items (From the OCR/Simulated Extraction)
            for ext_item in extracted.get("items", []):
                db.add(InvoiceItem(
                    invoice_id  = auto_inv.id,
                    po_item_id  = ext_item["po_item_id"],
                    description = ext_item["description"],
                    billed_qty  = ext_item["billed_qty"],
                    unit_price  = ext_item["unit_price"],
                    total_price = ext_item["total_price"]
                ))
            db.flush()

            # ── CRITICAL OCR GATE: If engine detected wrong invoice, block immediately ──
            if extracted.get("is_mismatch"):
                # Mark GRN as FAILED (audit trail, allows resubmission)
                grn.quality_status     = "GRN Payment Run: Failed"
                # Revert PO status so it re-appears in the dropdown for reprocessing
                if po:
                    po.status = "Sent to Vendor"
                auto_inv.match_status  = "Mismatch"
                auto_inv.match_notes   = "BLOCKED by OCR Engine: " + extracted.get("mismatch_reason", "Invoice items do not match this PO.")
                auto_inv.status        = "Under Review"
                auto_inv.payment_status = "On Hold"
                db.commit()
                db.refresh(auto_inv)
                return {
                    "status"       : "mismatch",
                    "match_status" : "Mismatch",
                    "message"      : auto_inv.match_notes,
                    "grn_number"   : grn.grn_number
                }

            # 3. Trigger the Strict 'Absolute-Zero-Variance' 3-Way Match
            # We verify PO vs GRN vs Invoice for every single decimal.
            issues = []
            
            # Count Verification
            if len(po.items) != len(extracted["items"]):
                issues.append(f"Item Count Mismatch: PO expects {len(po.items)} items, but Invoice has {len(extracted['items'])}.")
            
            # Line-Item wise Financial Audit
            grn_accepted_map = {gi.po_item_id: float(gi.accepted_qty or 0) for gi in grn.items}
            
            for po_item in po.items:
                ext_item = next((i for i in extracted["items"] if i.get("po_item_id") == po_item.id), None)
                if not ext_item:
                    issues.append(f"Missing Item: {po_item.description} not found in Invoice.")
                    continue
                
                # A. Unit Price Check
                if abs(float(po_item.unit_price) - float(ext_item["unit_price"])) > 0.01:
                    issues.append(f"Unit Price Discrepancy on '{po_item.description}': PO says {po_item.unit_price}, Invoice says {ext_item['unit_price']}.")
                
                # B. Item wise Amount & Tax Check
                accepted_qty = grn_accepted_map.get(po_item.id, 0)
                po_line_subtotal = accepted_qty * float(po_item.unit_price)
                po_line_tax      = po_line_subtotal * (float(po_item.tax_percent) / 100)
                
                ext_line_tax = float(ext_item.get("tax", 0))
                
                # Comparison
                if abs(po_line_subtotal - float(ext_item["total_price"])) > 0.05:
                    issues.append(f"Line Amount Mismatch on '{po_item.description}': Expected {po_line_subtotal} based on GRN, but Invoice says {ext_item['total_price']}.")
                
                if abs(po_line_tax - ext_line_tax) > 0.05:
                    issues.append(f"Line Tax Mismatch on '{po_item.description}': Expected tax {po_line_tax:.2f}, but Invoice tax is {ext_line_tax:.2f}.")

            # C. Grand Total Check — compare against GRN accepted qty amounts, not full PO total
            # This correctly handles partial deliveries.
            expected_total = sum(
                grn_accepted_map.get(po_item.id, 0)
                * float(po_item.unit_price)
                * (1 + float(po_item.tax_percent) / 100)
                for po_item in po.items
            )
            if abs(expected_total - float(extracted["total_amount"])) > 1.0:
                issues.append(
                    f"Grand Total Mismatch: Expected \u20b9{expected_total:,.2f} "
                    f"(GRN accepted qty \u00d7 PO prices incl. GST), "
                    f"Invoice shows \u20b9{extracted['total_amount']:,.2f}."
                )


            # ── FAIL GATE: If any issues found, mark all as FAILED for audit ──
            if issues or extracted.get("is_mismatch"):
                # Mark GRN as FAILED (audit trail, allows resubmission)
                grn.quality_status    = "GRN Payment Run: Failed"
                # Revert PO status so it re-appears in the dropdown for reprocessing
                if po:
                    po.status = "Sent to Vendor"
                auto_inv.match_status = "Mismatch"
                auto_inv.match_notes  = "FAILED: " + "; ".join(issues) if issues else extracted.get("mismatch_reason")
                auto_inv.status       = "Under Review"
                auto_inv.payment_status = "On Hold"
                db.commit()
                db.refresh(auto_inv)
                return {
                    "status"       : "mismatch",
                    "match_status" : "Mismatch",
                    "message"      : auto_inv.match_notes,
                    "grn_number"   : grn.grn_number
                }

            # 4. Trigger standard 3-way match logic if all literal counts matched
            try:
                three_way_match(auto_inv.id, db)
                db.refresh(auto_inv)
            except Exception as e:
                auto_inv.match_status = "Exception"
                auto_inv.match_notes = f"System Exception during Match: {str(e)}"
                db.commit()

            # 5. Create Automated Payment ONLY IF FULLY APPROVED/MATCHED
            if data.auto_settle and auto_inv.status == "Approved":
                auto_pay = Payment(
                    payment_ref    = generate_ref("PAY", db, Payment),
                    invoice_id     = auto_inv.id,
                    vendor_id      = data.vendor_id,
                    amount         = extracted["total_amount"],
                    payment_mode   = data.payment_method or "NEFT",
                    payment_date   = data.received_date,
                    status         = "Processed",
                    notes          = "Automatic Settlement (Touchless Pipeline Verified)"
                )
                db.add(auto_pay)
                auto_inv.payment_status = "Paid"
            else:
                auto_inv.payment_status = "On Hold" if auto_inv.status == "Under Review" else "Unpaid"

            db.commit()
            db.refresh(auto_inv)

            return {
                "status"       : "success",
                "match_status" : auto_inv.match_status,
                "message" : "Smart Receipt Created & Verified",
                "grn_number" : grn.grn_number
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"S2P Automation Layer Crash: {str(e)}")

    return {
        "status"      : "success",
        "match_status": "Pending",
        "message"     : "Smart Receipt Created & Verified",
        "grn_number"  : grn.grn_number
    }

# ── PAYMENT ROUTES ────────────────────────────────────────────

@router.post("/payments/")
def create_payment(data: PaymentCreate, db: Session = Depends(get_db)):
    from app.services.vendor_scorer import score_vendor   # local import avoids circular

    payment = Payment(
        payment_ref    = generate_ref("PAY", db, Payment),
        invoice_id     = data.invoice_id,
        vendor_id      = data.vendor_id,
        amount         = data.amount,
        payment_mode   = data.payment_mode,
        payment_date   = data.payment_date,
        bank_reference = data.bank_reference,
        notes          = data.notes,
        status         = "Processed"
    )
    db.add(payment)

    # Update invoice payment status
    invoice = db.query(Invoice).filter(Invoice.id == data.invoice_id).first()
    if invoice:
        paid = db.query(func.sum(Payment.amount)).filter(
            Payment.invoice_id == data.invoice_id
        ).scalar() or 0
        paid += data.amount
        if float(paid) >= float(invoice.total_amount):
            invoice.payment_status = "Paid"
            invoice.status         = "Paid"
        else:
            invoice.payment_status = "Partially Paid"

    db.commit()
    db.refresh(payment)

    log_action(
        table_name="payments",
        record_id=payment.id,
        action="CREATE",
        changed_by="system",
        old_values=None,
        new_values={"amount": float(payment.amount), "invoice_id": data.invoice_id},
        db=db
    )

    # ── BR-S2P-13: Auto-update vendor performance score ───────
    score_result = None
    try:
        score_result = score_vendor(data.vendor_id, db)
    except Exception:
        pass   # non-blocking — payment is already committed

    response = {"message": "Payment recorded", "payment": payment}
    if score_result:
        response["vendor_score_updated"] = {
            "vendor_id"    : data.vendor_id,
            "overall_score": score_result.get("overall_score"),
            "grade"        : score_result.get("grade"),
        }
    return response

@router.get("/payments/")
def get_payments(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    payments = db.query(Payment).options(joinedload(Payment.invoice)).order_by(Payment.payment_date.desc()).all()
    
    result = []
    for p in payments:
        vendor = db.query(Vendor).filter(Vendor.id == p.vendor_id).first() if p.vendor_id else None
        p_dict = {
            "id": p.id,
            "payment_ref": p.payment_ref,
            "invoice_id": p.invoice_id,
            "invoice_ref": p.invoice.invoice_number if p.invoice else "N/A",
            "vendor_id": p.vendor_id,
            "vendor_name": vendor.company_name if vendor else "Unknown Vendor",
            "amount": float(p.amount),
            "payment_mode": p.payment_mode,
            "payment_date": str(p.payment_date),
            "bank_reference": p.bank_reference,
            "status": p.status
        }
        result.append(p_dict)
        
    return {"payments": result}

# ── PAYMENT ALERTS (BR-S2P-11) — add at bottom of invoices.py ──

@router.get("/alerts/overdue")
def get_overdue_payments(db: Session = Depends(get_db)):
    """Invoices past due date — BR-S2P-11"""
    from datetime import date
    today    = date.today()
    invoices = db.query(Invoice).filter(
        Invoice.payment_status.in_(["Unpaid", "Partially Paid"]),
        Invoice.due_date < today,
        Invoice.due_date.isnot(None)
    ).all()
    result = []
    for inv in invoices:
        vendor   = db.query(Vendor).filter(Vendor.id == inv.vendor_id).first() if inv.vendor_id else None
        overdue_days = (today - inv.due_date).days
        result.append({
            "internal_ref"  : inv.internal_ref,
            "invoice_number": inv.invoice_number,
            "vendor_name"   : vendor.company_name if vendor else "Unknown",
            "total_amount"  : float(inv.total_amount),
            "due_date"      : str(inv.due_date),
            "overdue_days"  : overdue_days,
            "payment_status": inv.payment_status,
            "urgency"       : "CRITICAL" if overdue_days > 30 else "HIGH" if overdue_days > 15 else "MEDIUM"
        })
    result.sort(key=lambda x: x["overdue_days"], reverse=True)
    total_overdue = sum(r["total_amount"] for r in result)
    return {
        "total_overdue_invoices": len(result),
        "total_overdue_amount"  : round(total_overdue, 2),
        "invoices"              : result
    }