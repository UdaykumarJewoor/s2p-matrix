"""
scripts/migrate_vendor_portal.py
Run once to add vendor portal token columns to rfq_vendors table.
Usage: python scripts/migrate_vendor_portal.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from app.database import engine
from sqlalchemy import text

MIGRATIONS = [
    ("invite_token",  "ALTER TABLE rfq_vendors ADD COLUMN invite_token  VARCHAR(100) NULL UNIQUE"),
    ("token_expires", "ALTER TABLE rfq_vendors ADD COLUMN token_expires DATETIME NULL"),
    ("token_used",    "ALTER TABLE rfq_vendors ADD COLUMN token_used    TINYINT(1) NOT NULL DEFAULT 0"),
    ("email_status",  "ALTER TABLE rfq_vendors ADD COLUMN email_status  ENUM('Not Sent','Simulated','Sent','Failed') NOT NULL DEFAULT 'Not Sent'"),
]

def column_exists(conn, table, column):
    row = conn.execute(text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column}).scalar()
    return row > 0

def run():
    print("[*] Running vendor portal DB migration...")
    with engine.connect() as conn:
        for col, sql in MIGRATIONS:
            if column_exists(conn, "rfq_vendors", col):
                print(f"  [OK] Column '{col}' already exists - skipped")
            else:
                conn.execute(text(sql))
                conn.commit()
                print(f"  [ADDED] Column '{col}'")

        # Add index for fast token lookups if not exists
        idx = conn.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'rfq_vendors' "
            "AND INDEX_NAME = 'idx_rfq_vendors_token'"
        )).scalar()
        if not idx:
            conn.execute(text(
                "CREATE INDEX idx_rfq_vendors_token ON rfq_vendors (invite_token)"
            ))
            conn.commit()
            print("  [ADDED] Index idx_rfq_vendors_token created")
        else:
            print("  [OK] Index already exists - skipped")

    print("\n[DONE] Migration complete - rfq_vendors table updated.")

if __name__ == "__main__":
    run()
