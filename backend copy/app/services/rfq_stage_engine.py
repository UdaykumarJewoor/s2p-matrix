# services/rfq_stage_engine.py
# Single source of truth for RFQ stage progression.
# Both manual actions AND pipeline automation call this module.
# Rule: Once a stage is completed, it is NEVER re-executed or decremented.

from sqlalchemy.orm import Session
from app.models.rfq import RFQ
import logging

logger = logging.getLogger(__name__)


def get_rfq_current_stage(rfq_id: int, db: Session) -> int:
    """
    Determines the true current stage of an RFQ by scanning the DB facts.
    This is the ground truth — it checks actual child records, not just rfq.current_stage.
    Always returns the HIGHEST confirmed stage.

    Stage mapping:
      0 = RFQ created  (always true once RFQ exists)
      1 = RFQ loaded / validated
      2 = Vendors discovered / assigned
      3 = Quotations received
      4 = Quotation comparison done (winner selected)
      5 = Purchase Order created
      6 = GRN created (goods received)
      7 = Invoice matched (3-way match run)
      8 = Payment processed
    """
    from app.models.purchase_order import PurchaseOrder
    from app.models.invoice import Invoice, GRN
    from app.models.payment import Payment
    from app.models.quotation import Quotation
    from app.models.rfq import RFQVendor

    stage = 1  # RFQ exists, so Stage 1 is always confirmed

    # Stage 2: Vendors assigned
    vendor_count = db.query(RFQVendor).filter(RFQVendor.rfq_id == rfq_id).count()
    if vendor_count > 0:
        stage = 2

    # Stage 3: Quotations exist
    quote_count = db.query(Quotation).filter(Quotation.rfq_id == rfq_id).count()
    if quote_count > 0:
        stage = 3

    # Stage 4: A quotation has been selected/recommended
    selected = db.query(Quotation).filter(
        Quotation.rfq_id       == rfq_id,
        Quotation.is_recommended == True
    ).first()
    if selected:
        stage = 4

    # Stage 5: PO exists for this RFQ
    po = db.query(PurchaseOrder).filter(PurchaseOrder.rfq_id == rfq_id).first()
    if po:
        stage = 5

        # Stage 6: GRN exists for this PO
        grn = db.query(GRN).filter(GRN.po_id == po.id).first()
        if grn:
            stage = 6

        # Stage 7: Invoice exists and match has been run
        invoice = db.query(Invoice).filter(Invoice.po_id == po.id).first()
        if invoice and invoice.match_status in ("Matched", "Partial Match", "Mismatch"):
            stage = 7

        # Stage 8: Payment processed
        if invoice:
            payment = db.query(Payment).filter(Payment.invoice_id == invoice.id).first()
            if payment:
                stage = 8

    return stage


def advance_rfq_stage(rfq_id: int, new_stage: int, db: Session) -> None:
    """
    Advances the RFQ's current_stage to new_stage.
    STRICTLY forward-only: will never move the stage backwards.
    Called by both manual routes AND the automated pipeline.
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        logger.warning(f"advance_rfq_stage: RFQ {rfq_id} not found")
        return

    if new_stage > (rfq.current_stage or 0):
        rfq.current_stage = new_stage
        db.commit()
        logger.info(f"RFQ {rfq_id} advanced to stage {new_stage}")
    else:
        logger.debug(f"RFQ {rfq_id} already at stage {rfq.current_stage}, skip advancing to {new_stage}")
