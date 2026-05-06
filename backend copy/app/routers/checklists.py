# routers/checklists.py — BR-S2P-12 Procurement Checklist Engine
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, Enum, ForeignKey
from app.database import get_db, Base
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

router = APIRouter()

class Checklist(Base):
    __tablename__ = "checklists"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(255), nullable=False)
    category      = Column(Enum("Electronic","Mechanical","General"))
    version       = Column(String(10), default="1.0")
    is_active     = Column(Boolean, default=True)
    last_reviewed = Column(Date)
    next_review   = Column(Date)
    created_at    = Column(DateTime, default=datetime.utcnow)

class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id            = Column(Integer, primary_key=True, index=True)
    checklist_id  = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"))
    item_text     = Column(Text, nullable=False)
    is_mandatory  = Column(Boolean, default=True)
    sort_order    = Column(Integer, default=0)

class ChecklistItemIn(BaseModel):
    item_text    : str
    is_mandatory : Optional[bool] = True
    sort_order   : Optional[int]  = 0

class ChecklistCreate(BaseModel):
    name          : str
    category      : str
    review_months : Optional[int] = 3   # quarterly by default
    items         : List[ChecklistItemIn] = []

@router.get("/")
def get_checklists(db: Session = Depends(get_db)):
    checklists = db.query(Checklist).filter(Checklist.is_active == True).all()
    result = []
    today  = date.today()
    for c in checklists:
        items = db.query(ChecklistItem).filter(
            ChecklistItem.checklist_id == c.id
        ).order_by(ChecklistItem.sort_order).all()

        overdue = c.next_review and c.next_review < today

        result.append({
            "id"           : c.id,
            "name"         : c.name,
            "category"     : c.category,
            "version"      : c.version,
            "total_items"  : len(items),
            "mandatory"    : sum(1 for i in items if i.is_mandatory),
            "last_reviewed": str(c.last_reviewed) if c.last_reviewed else None,
            "next_review"  : str(c.next_review)   if c.next_review   else None,
            "review_overdue": overdue,
            "items"        : [{"id": i.id, "text": i.item_text,
                               "mandatory": i.is_mandatory,
                               "order": i.sort_order} for i in items]
        })
    return {"total": len(result), "checklists": result}

@router.post("/")
def create_checklist(data: ChecklistCreate, db: Session = Depends(get_db)):
    today = date.today()
    cl = Checklist(
        name          = data.name,
        category      = data.category,
        version       = "1.0",
        is_active     = True,
        last_reviewed = today,
        next_review   = today + relativedelta(months=data.review_months)
    )
    db.add(cl)
    db.flush()
    for i, item in enumerate(data.items):
        db.add(ChecklistItem(
            checklist_id = cl.id,
            item_text    = item.item_text,
            is_mandatory = item.is_mandatory,
            sort_order   = i
        ))
    db.commit()
    db.refresh(cl)
    return {"message": "Checklist created", "id": cl.id}

@router.post("/{checklist_id}/review")
def mark_reviewed(checklist_id: int, review_months: int = 3,
                  db: Session = Depends(get_db)):
    """Mark checklist as reviewed — resets quarterly cycle (BR-S2P-12)"""
    cl = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Checklist not found")
    today = date.today()
    # Bump version
    parts       = cl.version.split(".")
    cl.version  = f"{parts[0]}.{int(parts[1])+1}"
    cl.last_reviewed = today
    cl.next_review   = today + relativedelta(months=review_months)
    db.commit()
    return {
        "message"     : f"Checklist reviewed. Next review: {cl.next_review}",
        "new_version" : cl.version,
        "next_review" : str(cl.next_review)
    }

@router.post("/{checklist_id}/items")
def add_item(checklist_id: int, item: ChecklistItemIn,
             db: Session = Depends(get_db)):
    cl = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Checklist not found")
    db.add(ChecklistItem(
        checklist_id = checklist_id,
        item_text    = item.item_text,
        is_mandatory = item.is_mandatory,
        sort_order   = item.sort_order
    ))
    db.commit()
    return {"message": "Item added"}

@router.delete("/{checklist_id}/items/{item_id}")
def remove_item(checklist_id: int, item_id: int, db: Session = Depends(get_db)):
    item = db.query(ChecklistItem).filter(
        ChecklistItem.id == item_id,
        ChecklistItem.checklist_id == checklist_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"message": "Item removed"}

@router.get("/overdue")
def get_overdue_checklists(db: Session = Depends(get_db)):
    today = date.today()
    overdue = db.query(Checklist).filter(
        Checklist.next_review < today,
        Checklist.is_active  == True
    ).all()
    return {
        "overdue_count": len(overdue),
        "checklists"   : [{"id": c.id, "name": c.name,
                           "category": c.category,
                           "next_review": str(c.next_review),
                           "overdue_days": (today - c.next_review).days
                          } for c in overdue]
    }