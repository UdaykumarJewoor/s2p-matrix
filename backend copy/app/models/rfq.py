from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy import DECIMAL, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class RFQ(Base):
    __tablename__ = "rfq"

    id              = Column(Integer, primary_key=True, index=True)
    rfq_number      = Column(String(30), unique=True, nullable=False)
    title           = Column(String(255), nullable=False)
    description     = Column(Text)
    category_id     = Column(Integer, ForeignKey("commodity_categories.id"))
    target_category = Column(String(50)) # Added to store discovery category

    issue_date      = Column(Date, nullable=False)
    deadline        = Column(Date, nullable=False)

    status          = Column(
                        Enum("Draft", "Sent", "Responses Received",
                             "Evaluation", "Closed", "Cancelled"),
                        default="Draft"
                      )
    current_stage   = Column(Integer, default=0)   # 0=new, 1-8=last completed stage
    estimated_value = Column(DECIMAL(15, 2))
    currency        = Column(String(5), default="INR")

    created_by      = Column(String(100))
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items           = relationship("RFQItem", back_populates="rfq", cascade="all, delete")
    vendors         = relationship("RFQVendor", back_populates="rfq", cascade="all, delete")
    quotations      = relationship("Quotation", back_populates="rfq")


class RFQItem(Base):
    __tablename__ = "rfq_items"

    id            = Column(Integer, primary_key=True, index=True)
    rfq_id        = Column(Integer, ForeignKey("rfq.id", ondelete="CASCADE"))
    item_code     = Column(String(50))
    description   = Column(String(500), nullable=False)
    quantity      = Column(DECIMAL(10, 2), nullable=False)
    unit          = Column(String(20), default="PCS")
    specification = Column(Text)

    rfq           = relationship("RFQ", back_populates="items")


class RFQVendor(Base):
    __tablename__ = "rfq_vendors"

    id              = Column(Integer, primary_key=True, index=True)
    rfq_id          = Column(Integer, ForeignKey("rfq.id", ondelete="CASCADE"))
    vendor_id       = Column(Integer, ForeignKey("vendors.id"))
    sent_at         = Column(DateTime)
    response_status = Column(
                        Enum("Pending", "Responded", "Declined", "No Response"),
                        default="Pending"
                      )
    # Vendor portal token (used for secure quotation submission link)
    invite_token    = Column(String(100), unique=True, nullable=True, index=True)
    token_expires   = Column(DateTime, nullable=True)
    token_used      = Column(Boolean, default=False)   # True after first submission
    email_status    = Column(
                        Enum("Not Sent", "Simulated", "Sent", "Failed"),
                        default="Not Sent"
                      )

    rfq             = relationship("RFQ", back_populates="vendors")


class CommodityCategory(Base):
    __tablename__ = "commodity_categories"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(100), nullable=False)
    parent_category = Column(Enum("Electronic", "Mechanical", "Service"))
    description     = Column(Text)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)