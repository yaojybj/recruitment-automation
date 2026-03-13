from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import InterviewSlot, Position

router = APIRouter(prefix="/interview-slots", tags=["面试时间管理"])


class SlotCreate(BaseModel):
    position_id: int
    date: str
    start_time: str
    end_time: str
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None
    location: Optional[str] = None
    is_online: bool = False
    meeting_link: Optional[str] = None
    capacity: int = 1


class SlotBatchCreate(BaseModel):
    slots: list[SlotCreate]


class SlotUpdate(BaseModel):
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None
    location: Optional[str] = None
    is_online: Optional[bool] = None
    meeting_link: Optional[str] = None
    capacity: Optional[int] = None
    is_available: Optional[bool] = None


@router.get("")
def list_slots(
    position_id: int = None,
    available_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(InterviewSlot)
    if position_id:
        query = query.filter(InterviewSlot.position_id == position_id)
    if available_only:
        query = query.filter(InterviewSlot.is_available == True)
    slots = query.order_by(InterviewSlot.date, InterviewSlot.start_time).all()
    return [
        {
            "id": s.id,
            "position_id": s.position_id,
            "position_title": s.position.title if s.position else None,
            "date": s.date,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "interviewer_name": s.interviewer_name,
            "interviewer_email": s.interviewer_email,
            "location": s.location,
            "is_online": s.is_online,
            "meeting_link": s.meeting_link,
            "capacity": s.capacity,
            "booked_count": s.booked_count,
            "is_available": s.is_available,
        }
        for s in slots
    ]


@router.post("")
def create_slot(data: SlotCreate, db: Session = Depends(get_db)):
    position = db.query(Position).get(data.position_id)
    if not position:
        raise HTTPException(404, "岗位不存在")
    slot = InterviewSlot(**data.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return {"id": slot.id, "message": "时间段已创建"}


@router.post("/batch")
def create_slots_batch(data: SlotBatchCreate, db: Session = Depends(get_db)):
    created = []
    for s in data.slots:
        slot = InterviewSlot(**s.model_dump())
        db.add(slot)
        created.append(slot)
    db.commit()
    return {"message": f"创建了 {len(created)} 个时间段"}


@router.put("/{slot_id}")
def update_slot(slot_id: int, data: SlotUpdate, db: Session = Depends(get_db)):
    slot = db.query(InterviewSlot).get(slot_id)
    if not slot:
        raise HTTPException(404, "时间段不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(slot, key, val)
    db.commit()
    return {"message": "已更新"}


@router.delete("/{slot_id}")
def delete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(InterviewSlot).get(slot_id)
    if not slot:
        raise HTTPException(404, "时间段不存在")
    if slot.booked_count > 0:
        raise HTTPException(400, "该时间段已有预约，不能删除")
    db.delete(slot)
    db.commit()
    return {"message": "已删除"}
