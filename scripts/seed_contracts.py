import sys
import os
import random
from datetime import date, timedelta

# Add backend directory to path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

# Important: import ALL models before Database operations to prevent SQLAlchemy Mapper Init errors
from app.database import engine, Base, SessionLocal
from app.models.vendor import Vendor
from app.models.rfq import RFQ, RFQItem
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.invoice import GRN, Invoice
from app.models.payment import VendorPerformance, Payment
from app.routers.contracts import Contract

def seed_contracts():
    db = SessionLocal()
    
    # Check if contracts already exist
    existing = db.query(Contract).count()
    if existing > 0:
        print(f"Contracts already seeded ({existing} found). Proceeding to add more or you can clear first.")
    
    # Get some valid vendors
    vendors = db.query(Vendor).limit(10).all()
    if not vendors:
        print("Error: No vendors found. Please run seed_vendors.py first.")
        return

    today = date.today()
    
   # Sample Scenarios
    contract_data = [
        {
            "num": "CON-2025-0001",
            "title": "Facility CCTV Maintenance AMC",
            "type": "AMC",
            "start": today - timedelta(days=200),
            "end": today - timedelta(days=15), # Extends logic to Expired
            "alert": 30,
            "value": 450000.00,
            "notes": "Covers quarterly cleaning and firmware updates for warehouse cameras."
        },
        {
            "num": "CON-2025-0002",
            "title": "Raw Copper Rate Contract Q3",
            "type": "Rate Contract",
            "start": today - timedelta(days=365),
            "end": today + timedelta(days=20), # Expiring soon
            "alert": 60,
            "value": 1500000.00,
            "notes": "Agreed cap rate for bulk copper wire purchases."
        },
        {
            "num": "CON-2026-0003",
            "title": "Software Licensing - SAP Middleware",
            "type": "Annual",
            "start": today - timedelta(days=60),
            "end": today + timedelta(days=305), # Active
            "alert": 30,
            "value": 800000.00,
            "notes": "Annual subscription for SAP MM middleware connector."
        },
        {
            "num": "CON-2026-0004",
            "title": "Security Guard Services - Block B",
            "type": "Annual",
            "start": today - timedelta(days=400),
            "end": today - timedelta(days=35), # Expired
            "alert": 30,
            "value": 1200000.00,
            "notes": "Expired contract, needs urgent renewal or new vendor."
        },
        {
            "num": "CON-2026-0005",
            "title": "Fire Extinguisher Refilling AMC",
            "type": "AMC",
            "start": today - timedelta(days=10),
            "end": today + timedelta(days=355), # Active
            "alert": 30,
            "value": 65000.00,
            "notes": "Bi-annual audit and refilling of extinguishers in manufacturing plant."
        },
        {
            "num": "CON-2026-0006",
            "title": "One-Time Server Installation",
            "type": "One-Time",
            "start": today + timedelta(days=10),
            "end": today + timedelta(days=40), # Valid, starts in future
            "alert": 10,
            "value": 250000.00,
            "notes": "Draft agreement for upcoming IT network overhaul."
        }
    ]

    for data in contract_data:
        # Determine status
        if data["end"] < today:
            status = "Expired"
        elif today >= (data["end"] - timedelta(days=data["alert"])):
            status = "Expiring Soon"
        elif data["start"] <= today:
            status = "Active"
        else:
            status = "Draft"

        c = Contract(
            contract_number=data["num"],
            vendor_id=random.choice(vendors).id,
            title=data["title"],
            contract_type=data["type"],
            start_date=data["start"],
            end_date=data["end"],
            renewal_alert_days=data["alert"],
            contract_value=data["value"],
            status=status,
            notes=data["notes"]
        )
        db.add(c)

    db.commit()
    print("✅ Successfully seeded 6 Contracts into the database!")
    db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_contracts()
