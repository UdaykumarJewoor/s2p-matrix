import sys
import os
import random
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models.negotiation import Negotiation

def seed_historical():
    db = SessionLocal()
    try:
        months_back = [1, 2, 3] 
        for m in months_back:
            dt = datetime.utcnow() - timedelta(days=30 * m)
            initial = random.randint(300000, 900000)
            agreed = initial - random.randint(25000, 95000)
            savings = initial - agreed
            savings_pct = round((savings / initial) * 100, 2)
            
            neg = Negotiation(
                quotation_id=1, 
                vendor_id=m, 
                negotiation_ref=f"NEG-HIST-{m}",
                round_number=1,
                initial_price=initial,
                current_offer=agreed,
                target_price=agreed - 10000,
                agreed_price=agreed,
                savings_achieved=savings,
                savings_percent=savings_pct,
                status="Agreed",
                created_at=dt,
                updated_at=dt
            )
            db.add(neg)
            
        db.commit()
        print("Success")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_historical()
