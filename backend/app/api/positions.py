from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Position, Resume, ScreeningRule
from ..schemas import PositionCreate, PositionUpdate, PositionOut

router = APIRouter(prefix="/positions", tags=["岗位管理"])


@router.get("", response_model=list[PositionOut])
def list_positions(is_active: bool = None, db: Session = Depends(get_db)):
    query = db.query(Position)
    if is_active is not None:
        query = query.filter(Position.is_active == is_active)
    positions = query.order_by(Position.created_at.desc()).all()

    result = []
    for p in positions:
        count = db.query(func.count(Resume.id)).filter(Resume.position_id == p.id).scalar()
        out = PositionOut.model_validate(p)
        out.resume_count = count
        result.append(out)
    return result


@router.get("/{position_id}", response_model=PositionOut)
def get_position(position_id: int, db: Session = Depends(get_db)):
    p = db.query(Position).get(position_id)
    if not p:
        raise HTTPException(404, "岗位不存在")
    count = db.query(func.count(Resume.id)).filter(Resume.position_id == p.id).scalar()
    out = PositionOut.model_validate(p)
    out.resume_count = count
    return out


@router.post("", response_model=PositionOut)
def create_position(data: PositionCreate, db: Session = Depends(get_db)):
    p = Position(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    out = PositionOut.model_validate(p)
    out.resume_count = 0
    return out


@router.put("/{position_id}", response_model=PositionOut)
def update_position(position_id: int, data: PositionUpdate, db: Session = Depends(get_db)):
    p = db.query(Position).get(position_id)
    if not p:
        raise HTTPException(404, "岗位不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(p, key, val)
    db.commit()
    db.refresh(p)
    count = db.query(func.count(Resume.id)).filter(Resume.position_id == p.id).scalar()
    out = PositionOut.model_validate(p)
    out.resume_count = count
    return out


@router.delete("/{position_id}")
def delete_position(position_id: int, db: Session = Depends(get_db)):
    p = db.query(Position).get(position_id)
    if not p:
        raise HTTPException(404, "岗位不存在")
    db.delete(p)
    db.commit()
    return {"message": "已删除"}
