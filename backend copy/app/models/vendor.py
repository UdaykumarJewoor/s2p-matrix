# models/vendor.py — Vendor & related table models
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy import DECIMAL, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Vendor(Base):
    __tablename__ = "vendors"

    id                = Column(Integer, primary_key=True, index=True)
    vendor_code       = Column(String(20), unique=True, nullable=False)
    company_name      = Column(String(255), nullable=False)
    contact_person    = Column(String(100))
    email             = Column(String(150), unique=True, nullable=False)
    phone             = Column(String(20))
    address           = Column(Text)
    city              = Column(String(100))
    state             = Column(String(100))
    pincode           = Column(String(10))
    country           = Column(String(100), default="India")

    category          = Column(Enum("Electronic", "Mechanical", "Both"), nullable=False)
    vendor_type       = Column(Enum("OEM", "Distributor", "Trader", "Service"), default="Distributor")

    oem_approved      = Column(Boolean, default=False)
    oem_brand         = Column(String(255))
    gst_number        = Column(String(20))
    pan_number        = Column(String(15))
    msme_registered   = Column(Boolean, default=False)

    status            = Column(
                            Enum("Pending", "Under Review", "Approved",
                                 "Blacklisted", "Inactive"),
                            default="Pending"
                        )
    approved_by       = Column(String(100))
    approved_at       = Column(DateTime)

    performance_score = Column(DECIMAL(5, 2), default=0.00)
    sap_vendor_code   = Column(String(20))

    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by        = Column(String(100), default="system")

    # Relationships
    documents         = relationship("VendorDocument", back_populates="vendor",
                                     cascade="all, delete")
    quotations        = relationship("Quotation", back_populates="vendor")
    purchase_orders   = relationship("PurchaseOrder", back_populates="vendor")
    performance       = relationship("VendorPerformance", back_populates="vendor")


class VendorDocument(Base):
    __tablename__ = "vendor_documents"

    id          = Column(Integer, primary_key=True, index=True)
    vendor_id   = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"))
    doc_type    = Column(Enum("GST Certificate", "PAN Card", "OEM Letter",
                              "Bank Details", "MSME Certificate", "Other"))
    file_name   = Column(String(255))
    file_path   = Column(String(500))
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    vendor      = relationship("Vendor", back_populates="documents")

# Ensure relationships to these models resolve correctly
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.payment import VendorPerformance
