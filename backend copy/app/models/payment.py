# models/payment.py
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy import DECIMAL, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id            = Column(Integer, primary_key=True, index=True)
    payment_ref   = Column(String(30), unique=True, nullable=False)
    invoice_id    = Column(Integer, ForeignKey("invoices.id"))
    vendor_id     = Column(Integer, ForeignKey("vendors.id"))

    amount        = Column(DECIMAL(15, 2), nullable=False)
    currency      = Column(String(5), default="INR")
    payment_mode  = Column(
                     Enum("NEFT", "RTGS", "IMPS", "Cheque", "UPI", "Auto-Transfer"),
                     default="NEFT"
                   )

    payment_date  = Column(Date, nullable=False)
    value_date    = Column(Date)
    bank_reference = Column(String(100))

    status        = Column(
                     Enum("Scheduled", "Processed", "Failed", "Returned"),
                     default="Scheduled"
                   )

    created_at    = Column(DateTime, default=datetime.utcnow)
    notes         = Column(Text)

    # Relationships
    invoice       = relationship("Invoice", back_populates="payments")


class VendorPerformance(Base):
    __tablename__ = "vendor_performance"

    id                  = Column(Integer, primary_key=True, index=True)
    vendor_id           = Column(Integer, ForeignKey("vendors.id"))
    evaluation_period   = Column(String(20), nullable=False)

    delivery_score      = Column(DECIMAL(5, 2), default=0.00)
    quality_score       = Column(DECIMAL(5, 2), default=0.00)
    pricing_score       = Column(DECIMAL(5, 2), default=0.00)
    response_score      = Column(DECIMAL(5, 2), default=0.00)
    overall_score       = Column(DECIMAL(5, 2), default=0.00)

    total_orders        = Column(Integer, default=0)
    on_time_deliveries  = Column(Integer, default=0)
    quality_rejections  = Column(Integer, default=0)
    rfqs_received       = Column(Integer, default=0)
    rfqs_responded      = Column(Integer, default=0)

    evaluated_at        = Column(DateTime, default=datetime.utcnow)
    notes               = Column(Text)

    vendor              = relationship("Vendor", back_populates="performance")