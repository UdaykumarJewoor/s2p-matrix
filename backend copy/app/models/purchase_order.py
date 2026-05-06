# models/purchase_order.py
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy import DECIMAL, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id               = Column(Integer, primary_key=True, index=True)
    po_number        = Column(String(30), unique=True, nullable=False)
    vendor_id        = Column(Integer, ForeignKey("vendors.id"))
    quotation_id     = Column(Integer, ForeignKey("quotations.id"))
    rfq_id           = Column(Integer, ForeignKey("rfq.id"))

    po_date          = Column(Date, nullable=False)
    delivery_date    = Column(Date)

    subtotal         = Column(DECIMAL(15, 2), default=0.00)
    tax_amount       = Column(DECIMAL(15, 2), default=0.00)
    total_amount     = Column(DECIMAL(15, 2), nullable=False)
    currency         = Column(String(5), default="INR")

    payment_terms    = Column(String(100))
    incoterms        = Column(String(100), default="DAP — Gandhinagar")
    department       = Column(String(50), default="Procurement")
    delivery_address = Column(Text)

    status           = Column(
                         Enum("Draft", "Pending L1 Approval", "Pending L2 Approval",
                              "Approved", "Sent to Vendor", "Acknowledged",
                              "Partially Received", "Received", "Closed", "Cancelled"),
                         default="Draft"
                       )
    l1_approver      = Column(String(100))
    l1_approved_at   = Column(DateTime)
    l2_approver      = Column(String(100))
    l2_approved_at   = Column(DateTime)

    sap_po_number    = Column(String(20))
    created_by       = Column(String(100))
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes            = Column(Text)

    # Relationships
    vendor           = relationship("Vendor", back_populates="purchase_orders")
    items            = relationship("POItem", back_populates="po", cascade="all, delete")
    grns             = relationship("GRN", back_populates="po")
    invoices         = relationship("Invoice", back_populates="po")


class POItem(Base):
    __tablename__ = "po_items"

    id           = Column(Integer, primary_key=True, index=True)
    po_id        = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    item_code    = Column(String(50))
    description  = Column(String(500), nullable=False)
    quantity     = Column(DECIMAL(10, 2), nullable=False)
    unit         = Column(String(20), default="PCS")
    unit_price   = Column(DECIMAL(15, 2), nullable=False)
    tax_percent  = Column(DECIMAL(5, 2), default=18.00)
    total_price  = Column(DECIMAL(15, 2), nullable=False)
    received_qty = Column(DECIMAL(10, 2), default=0.00)

    po           = relationship("PurchaseOrder", back_populates="items")