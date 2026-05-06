# routers/audit.py — View audit trail (NFR-06)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.utils.audit import AuditLog
from typing import Optional

router = APIRouter()

@router.get("/")
def get_audit_log(
    table_name : Optional[str] = None,
    action     : Optional[str] = None,
    limit      : int = 100,
    db         : Session = Depends(get_db)
):
    query = db.query(AuditLog).order_by(AuditLog.changed_at.desc())
    if table_name:
        query = query.filter(AuditLog.table_name == table_name)
    if action:
        query = query.filter(AuditLog.action == action)
    logs = query.limit(limit).all()
    return {
        "total": len(logs),
        "logs" : [{
            "id"        : l.id,
            "table"     : l.table_name,
            "record_id" : l.record_id,
            "action"    : l.action,
            "changed_by": l.changed_by,
            "changed_at": str(l.changed_at),
            "old_values": l.old_values,
            "new_values": l.new_values
        } for l in logs]
    }