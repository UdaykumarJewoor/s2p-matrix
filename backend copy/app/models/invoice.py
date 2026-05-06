# models/invoice.py
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy import DECIMAL, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id               = Column(Integer, primary_key=True, index=True)
    invoice_number   = Column(String(50), nullable=False)
    internal_ref     = Column(String(30), unique=True)
    vendor_id        = Column(Integer, ForeignKey("vendors.id"))
    po_id            = Column(Integer, ForeignKey("purchase_orders.id"))
    grn_id           = Column(Integer, ForeignKey("grn.id"))

    invoice_date     = Column(Date, nullable=False)
    received_date    = Column(Date)
    due_date         = Column(Date)

    subtotal         = Column(DECIMAL(15, 2), default=0.00)
    tax_amount       = Column(DECIMAL(15, 2), default=0.00)
    total_amount     = Column(DECIMAL(15, 2), nullable=False)
    currency         = Column(String(5), default="INR")

    match_status     = Column(
                         Enum("Pending", "Matched", "Partial Match",
                              "Mismatch", "Exception"),
                         default="Pending"
                       )
    match_notes      = Column(Text)
    payment_status   = Column(
                         Enum("Unpaid", "Partially Paid", "Paid", "On Hold"),
                         default="Unpaid"
                       )
    is_duplicate     = Column(Boolean, default=False)

    status           = Column(
                         Enum("Received", "Under Review", "Approved",
                              "Rejected", "Paid"),
                         default="Received"
                       )
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    vendor           = relationship("Vendor")
    po               = relationship("PurchaseOrder", back_populates="invoices")
    payments         = relationship("Payment", back_populates="invoice")
    items            = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id            = Column(Integer, primary_key=True, index=True)
    invoice_id    = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    po_item_id    = Column(Integer, ForeignKey("po_items.id"))
    description   = Column(String(500))
    billed_qty    = Column(DECIMAL(10, 2), nullable=False)
    unit_price    = Column(DECIMAL(15, 2), nullable=False)
    total_price   = Column(DECIMAL(15, 2), nullable=False)

    invoice       = relationship("Invoice", back_populates="items")


class GRN(Base):
    __tablename__ = "grn"

    id              = Column(Integer, primary_key=True, index=True)
    grn_number      = Column(String(30), unique=True, nullable=False)
    po_id           = Column(Integer, ForeignKey("purchase_orders.id"))
    vendor_id       = Column(Integer, ForeignKey("vendors.id"))
    received_date   = Column(Date, nullable=False)
    received_by     = Column(String(100))

    quality_status  = Column(
                        Enum("Accepted", "Partially Accepted", "Rejected", "GRN Payment Run: Failed"),
                        default="Accepted"
                      )
    rejection_reason = Column(Text)
    sap_grn_number  = Column(String(20))
    created_at      = Column(DateTime, default=datetime.utcnow)
    notes           = Column(Text)

    # Relationships
    po              = relationship("PurchaseOrder", back_populates="grns")
    items           = relationship("GRNItem", back_populates="grn", cascade="all, delete")


class GRNItem(Base):
    __tablename__ = "grn_items"

    id            = Column(Integer, primary_key=True, index=True)
    grn_id        = Column(Integer, ForeignKey("grn.id", ondelete="CASCADE"))
    po_item_id    = Column(Integer, ForeignKey("po_items.id"))
    description   = Column(String(500))
    ordered_qty   = Column(DECIMAL(10, 2))
    received_qty  = Column(DECIMAL(10, 2), nullable=False)
    accepted_qty  = Column(DECIMAL(10, 2))
    rejected_qty  = Column(DECIMAL(10, 2), default=0.00)

    grn           = relationship("GRN", back_populates="items")