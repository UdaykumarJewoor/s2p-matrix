# routers/contracts.py — BR-S2P-07 Contract Management
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.vendor import Vendor
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timedelta

router = APIRouter()

# ── Inline model (no separate file needed) ───────────────────
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, DECIMAL, Enum, ForeignKey, Boolean
from app.database import Base

class Contract(Base):
    __tablename__ = "contracts"
    id                  = Column(Integer, primary_key=True, index=True)
    contract_number     = Column(String(30), unique=True, nullable=False)
    vendor_id           = Column(Integer, ForeignKey("vendors.id"))
    title               = Column(String(255), nullable=False)
    contract_type       = Column(Enum("Annual","One-Time","AMC","Rate Contract"), default="Annual")
    start_date          = Column(Date, nullable=False)
    end_date            = Column(Date, nullable=False)
    renewal_alert_days  = Column(Integer, default=30)
    contract_value      = Column(DECIMAL(15,2))
    status              = Column(Enum("Draft","Active","Expiring Soon","Expired","Terminated"), default="Draft")
    file_path           = Column(String(500))
    created_at          = Column(DateTime, default=datetime.utcnow)
    notes               = Column(Text)

# ── Schemas ───────────────────────────────────────────────────
class ContractCreate(BaseModel):
    vendor_id          : int
    title              : str
    contract_type      : Optional[str] = "Annual"
    start_date         : date
    end_date           : date
    renewal_alert_days : Optional[int] = 30
    contract_value     : Optional[float] = None
    notes              : Optional[str] = None

def generate_contract_number(db: Session) -> str:
    year  = datetime.now().year
    max_id = db.query(func.max(Contract.id)).scalar() or 0
    return f"CON-{year}-{str(max_id + 1).zfill(4)}"

def update_contract_status(contract: Contract) -> str:
    today = date.today()
    if contract.end_date < today:
        return "Expired"
    alert_date = contract.end_date - timedelta(days=contract.renewal_alert_days or 30)
    if today >= alert_date:
        return "Expiring Soon"
    if contract.start_date <= today:
        return "Active"
    return "Draft"

# ── ROUTES ────────────────────────────────────────────────────
@router.get("/")
def get_contracts(status: Optional[str] = None, db: Session = Depends(get_db)):
    contracts = db.query(Contract).all()
    # Auto-update statuses
    for c in contracts:
        new_status = update_contract_status(c)
        if c.status != new_status and c.status != "Terminated":
            c.status = new_status
    db.commit()
    if status:
        contracts = [c for c in contracts if c.status == status]
    result = []
    for c in contracts:
        vendor = db.query(Vendor).filter(Vendor.id == c.vendor_id).first()
        days_left = (c.end_date - date.today()).days
        result.append({
            "id"                : c.id,
            "contract_number"   : c.contract_number,
            "vendor_id"         : c.vendor_id,
            "vendor_name"       : vendor.company_name if vendor else "Unknown",
            "title"             : c.title,
            "contract_type"     : c.contract_type,
            "start_date"        : str(c.start_date),
            "end_date"          : str(c.end_date),
            "days_remaining"    : days_left,
            "contract_value"    : float(c.contract_value) if c.contract_value else None,
            "renewal_alert_days": c.renewal_alert_days,
            "status"            : c.status,
            "notes"             : c.notes,
            "created_at"        : str(c.created_at)
        })
    expiring = sum(1 for r in result if r["status"] == "Expiring Soon")
    expired  = sum(1 for r in result if r["status"] == "Expired")
    return {
        "total"         : len(result),
        "expiring_soon" : expiring,
        "expired"       : expired,
        "contracts"     : result
    }

@router.get("/{contract_id}")
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    return c

@router.post("/")
def create_contract(data: ContractCreate, db: Session = Depends(get_db)):
    c = Contract(
        contract_number    = generate_contract_number(db),
        vendor_id          = data.vendor_id,
        title              = data.title,
        contract_type      = data.contract_type,
        start_date         = data.start_date,
        end_date           = data.end_date,
        renewal_alert_days = data.renewal_alert_days,
        contract_value     = data.contract_value,
        notes              = data.notes,
        status             = "Draft"
    )
    c.status = update_contract_status(c)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"message": "Contract created", "contract_number": c.contract_number, "contract": c}

@router.post("/{contract_id}/terminate")
def terminate_contract(contract_id: int, db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    c.status = "Terminated"
    db.commit()
    return {"message": f"Contract {c.contract_number} terminated"}

@router.get("/alerts/expiring")
def get_expiring_contracts(db: Session = Depends(get_db)):
    """Returns contracts expiring within their alert window — BR-S2P-07"""
    contracts = db.query(Contract).all()
    alerts = []
    today  = date.today()
    for c in contracts:
        if c.status in ["Expired", "Terminated"]:
            continue
        days_left = (c.end_date - today).days
        if days_left <= (c.renewal_alert_days or 30):
            vendor = db.query(Vendor).filter(Vendor.id == c.vendor_id).first()
            alerts.append({
                "contract_number": c.contract_number,
                "title"          : c.title,
                "vendor_name"    : vendor.company_name if vendor else "Unknown",
                "end_date"       : str(c.end_date),
                "days_remaining" : days_left,
                "status"         : "EXPIRED" if days_left < 0 else "EXPIRING SOON"
            })
    alerts.sort(key=lambda x: x["days_remaining"])
    return {"total_alerts": len(alerts), "alerts": alerts}
# ── AMC ROUTES (BR-S2P-14) ────────────────────────────────────

@router.get("/amc/all")
def get_amc_contracts(db: Session = Depends(get_db)):
    """All Annual Maintenance Contracts"""
    amcs  = db.query(Contract).filter(Contract.contract_type == "AMC").all()
    today = date.today()
    result = []
    for c in amcs:
        vendor    = db.query(Vendor).filter(Vendor.id == c.vendor_id).first()
        days_left = (c.end_date - today).days
        result.append({
            "id"             : c.id,
            "contract_number": c.contract_number,
            "vendor_name"    : vendor.company_name if vendor else "Unknown",
            "title"          : c.title,
            "start_date"     : str(c.start_date),
            "end_date"       : str(c.end_date),
            "days_remaining" : days_left,
            "contract_value" : float(c.contract_value) if c.contract_value else None,
            "status"         : c.status,
            "alert"          : days_left <= (c.renewal_alert_days or 30)
        })
    result.sort(key=lambda x: x["days_remaining"])
    return {"total": len(result), "amc_contracts": result}