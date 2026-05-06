import sys
import os
import random
from datetime import datetime, timedelta

# Add backend dir to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.database import SessionLocal
from app.models.negotiation import Negotiation

db = SessionLocal()

def seed_historical():
    try:
        # Create historical entries for Jan, Feb, Mar 2026
        months_back = [1, 2, 3] # Apr is 0. So 1 month back is Mar, 2 is Feb, 3 is Jan
        
        for m in months_back:
            # Approximate date
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
        print("Successfully seeded historical negotiation data for chart!")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_historical()
