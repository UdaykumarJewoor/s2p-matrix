# utils/audit.py — NFR-06 Full Audit Trail
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum
from app.database import Base, SessionLocal
from datetime import datetime

class AuditLog(Base):
    __tablename__ = "audit_log"
    id         = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(50), nullable=False)
    record_id  = Column(Integer,   nullable=False)
    action     = Column(Enum("CREATE","UPDATE","DELETE","APPROVE",
                             "REJECT","SEND","MATCH","SYNC"), nullable=False)
    changed_by = Column(String(100), default="system")
    changed_at = Column(DateTime, default=datetime.utcnow)
    old_values = Column(JSON)
    new_values = Column(JSON)
    ip_address = Column(String(45))

def log_action(
    table_name : str,
    record_id  : int,
    action     : str,
    changed_by : str  = "system",
    old_values : dict = None,
    new_values : dict = None,
    db         : Session = None
):
    """Call this from any router to log an action"""
    should_close = False
    if db is None:
        db          = SessionLocal()
        should_close = True
    try:
        entry = AuditLog(
            table_name = table_name,
            record_id  = record_id,
            action     = action,
            changed_by = changed_by,
            changed_at = datetime.utcnow(),
            old_values = old_values,
            new_values = new_values
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        print(f"Audit log error: {e}")
    finally:
        if should_close:
            db.close()