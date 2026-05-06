import sys
import os
from sqlalchemy.orm import Session

# Add backend to path so we can import app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.database import SessionLocal
from app.models.vendor import Vendor
from app.models.rfq import RFQ, RFQItem
from app.services.email_service import send_rfq_invitation, generate_vendor_token

def send_test_rfq():
    db = SessionLocal()
    try:
        # Get the vendor
        vendor = db.query(Vendor).filter(Vendor.id == 273).first()
        if not vendor:
            print("Vendor not found!")
            return

        # Get a dummy RFQ (RFQ-2026-0001)
        rfq = db.query(RFQ).filter(RFQ.id == 1).first()
        if not rfq:
            print("RFQ not found!")
            return

        # Get RFQ items
        items_objs = db.query(RFQItem).filter(RFQItem.rfq_id == rfq.id).all()
        items = [{"description": i.description, "quantity": i.quantity} for i in items_objs]

        token = generate_vendor_token()
        
        print(f"Attempting to send RFQ {rfq.rfq_number} to {vendor.email}...")
        
        # We call the service function
        result = send_rfq_invitation(
            vendor_email=vendor.email,
            vendor_name=vendor.company_name,
            contact_person=vendor.contact_person or "Udaykumar",
            rfq_number=rfq.rfq_number,
            rfq_title=rfq.title,
            deadline=str(rfq.deadline),
            items=items,
            token=token
        )
        
        print("\nResult:")
        print(result)
        
        if result.get("status") == "simulated":
            print("\nNOTE: The system is in SIMULATE mode. No real email was sent.")
            print("To send real emails, you need to configure SMTP in your .env file.")
        
    finally:
        db.close()

if __name__ == "__main__":
    send_test_rfq()
