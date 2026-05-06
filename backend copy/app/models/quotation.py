# models/quotation.py
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy import DECIMAL, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Quotation(Base):
    __tablename__ = "quotations"

    id                  = Column(Integer, primary_key=True, index=True)
    quotation_number    = Column(String(30), unique=True, nullable=False)
    rfq_id              = Column(Integer, ForeignKey("rfq.id"))
    vendor_id           = Column(Integer, ForeignKey("vendors.id"))

    submitted_at        = Column(DateTime, default=datetime.utcnow)
    valid_until         = Column(Date)

    subtotal            = Column(DECIMAL(15, 2), default=0.00)
    tax_amount          = Column(DECIMAL(15, 2), default=0.00)
    total_amount        = Column(DECIMAL(15, 2), default=0.00)
    currency            = Column(String(5), default="INR")

    payment_terms       = Column(String(100))
    delivery_days       = Column(Integer)
    warranty_months     = Column(Integer, default=0)

    ai_score            = Column(DECIMAL(5, 2), default=0.00)
    ai_recommendation   = Column(Text)
    is_recommended      = Column(Boolean, default=False)

    status              = Column(
                            Enum("Received", "Under Evaluation",
                                 "Selected", "Rejected"),
                            default="Received"
                          )
    notes               = Column(Text)

    # Relationships
    rfq                 = relationship("RFQ", back_populates="quotations")
    vendor              = relationship("Vendor", back_populates="quotations")
    items               = relationship("QuotationItem", back_populates="quotation",
                                       cascade="all, delete")


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id              = Column(Integer, primary_key=True, index=True)
    quotation_id    = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"))
    rfq_item_id     = Column(Integer, ForeignKey("rfq_items.id"))
    description     = Column(String(500), nullable=False)
    quantity        = Column(DECIMAL(10, 2), nullable=False)
    unit_price      = Column(DECIMAL(15, 2), nullable=False)
    tax_percent     = Column(DECIMAL(5, 2), default=18.00)
    total_price     = Column(DECIMAL(15, 2), nullable=False)

    quotation       = relationship("Quotation", back_populates="items")