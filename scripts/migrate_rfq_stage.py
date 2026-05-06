"""
Migration: Add current_stage column to rfq table
Run this once to enable the state-aware pipeline engine.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='s2p_matrix' AND TABLE_NAME='rfq' AND COLUMN_NAME='current_stage'"
        ))
        exists = result.fetchone()

        if not exists:
            conn.execute(text("ALTER TABLE rfq ADD COLUMN current_stage INT NOT NULL DEFAULT 0"))
            conn.commit()
            print("SUCCESS: current_stage column added to rfq table")
            print("All existing RFQs will start with stage=0 (will be auto-detected on first scan)")
        else:
            print("INFO: current_stage column already exists — no changes made")

        # Show current state of rfqs
        rows = conn.execute(text("SELECT id, rfq_number, status, current_stage FROM rfq ORDER BY id LIMIT 10")).fetchall()
        print("\nCurrent RFQ stages:")
        for r in rows:
            print(f"  RFQ #{r[0]}: {r[1]} | status={r[2]} | current_stage={r[3]}")

if __name__ == "__main__":
    run_migration()
