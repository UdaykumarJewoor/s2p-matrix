import sys
import os
import random
import json
from datetime import datetime, timedelta

# Add backend directory to path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import engine, Base, SessionLocal
from app.utils.audit import AuditLog

def seed_audits():
    db = SessionLocal()
    
    existing = db.query(AuditLog).count()
    if existing > 0:
        print(f"Audit logs already exist ({existing}). Proceeding to add more.")

    now = datetime.now()
    
    logs_data = [
        {
            "table": "rfq", "record_id": 1, "action": "CREATE", "by": "system",
            "at": now - timedelta(days=2, hours=4),
            "old": None,
            "new": {"status": "Draft", "rfq_number": "RFQ-2026-0001"}
        },
        {
            "table": "vendors", "record_id": 42, "action": "APPROVE", "by": "Pradeep Sharma",
            "at": now - timedelta(days=1, hours=8),
            "old": {"status": "Pending"},
            "new": {"status": "Approved"}
        },
        {
            "table": "rfq", "record_id": 1, "action": "UPDATE", "by": "Rahul Joshi",
            "at": now - timedelta(days=1, hours=2),
            "old": {"estimated_value": 450000.00},
            "new": {"estimated_value": 500000.00}
        },
        {
            "table": "quotations", "record_id": 105, "action": "CREATE", "by": "Vendor Portal",
            "at": now - timedelta(hours=14),
            "old": None,
            "new": {"status": "Received", "total_amount": 420000.00}
        },
        {
            "table": "purchase_orders", "record_id": 55, "action": "APPROVE", "by": "Sneha Patel",
            "at": now - timedelta(hours=5),
            "old": {"status": "Pending L1 Approval"},
            "new": {"status": "Pending L2 Approval", "l1_approver": "Sneha Patel"}
        },
        {
            "table": "purchase_orders", "record_id": 55, "action": "APPROVE", "by": "Ravi Beli",
            "at": now - timedelta(hours=2),
            "old": {"status": "Pending L2 Approval"},
            "new": {"status": "Approved", "l2_approver": "Ravi Beli"}
        },
        {
            "table": "invoices", "record_id": 312, "action": "UPDATE", "by": "ai-matching-engine",
            "at": now - timedelta(minutes=45),
            "old": {"match_status": "Pending"},
            "new": {"match_status": "Matched"}
        },
        {
            "table": "contracts", "record_id": 3, "action": "UPDATE", "by": "Legal Team",
            "at": now - timedelta(minutes=15),
            "old": {"end_date": "2026-05-01"},
            "new": {"end_date": "2027-05-01", "notes": "Renewed for 1 extra year."}
        }
    ]

    for data in logs_data:
        log = AuditLog(
            table_name=data["table"],
            record_id=data["record_id"],
            action=data["action"],
            changed_by=data["by"],
            changed_at=data["at"],
            old_values=data["old"],
            new_values=data["new"]
        )
        db.add(log)

    db.commit()
    print("✅ Successfully seeded 8 Audit Logs into the database!")
    db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_audits()
