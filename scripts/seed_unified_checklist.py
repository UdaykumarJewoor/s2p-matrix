import sys
import os
from datetime import date
from sqlalchemy.orm import Session

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import SessionLocal, engine
from app.routers.checklists import Checklist, ChecklistItem

def seed_unified_checklist():
    db: Session = SessionLocal()
    
    # Unified Checklist for both (Generalized)
    unified_cl = Checklist(
        name="Unified Procurement Compliance & Audit Checklist",
        category="General",
        version="1.0",
        is_active=True,
        last_reviewed=date(2024, 1, 15),
        next_review=date(2024, 4, 15) # Intentionally overdue for demo
    )
    db.add(unified_cl)
    db.flush()
    
    items = [
        ("Verify Vendor KYC and GST registration status", True),
        ("Confirm active NDA (Non-Disclosure Agreement) is on file", True),
        ("Check for any active debarment or blacklisting records", True),
        ("Audit last 3 months of rejection rate data", False),
        ("Confirm Vendor OEM/Factory inspection validity", True),
        ("Review environmental and safety compliance certificates", False)
    ]
    
    for i, (text, mandatory) in enumerate(items):
        db.add(ChecklistItem(
            checklist_id=unified_cl.id,
            item_text=text,
            is_mandatory=mandatory,
            sort_order=i
        ))
    
    db.commit()
    print("Successfully seeded Unified Procurement Checklist (Category: General).")
    print("Note: This checklist is set as 'Overdue' for demonstration purposes.")
    db.close()

if __name__ == "__main__":
    seed_unified_checklist()
