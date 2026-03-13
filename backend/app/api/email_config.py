from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EmailConfig
from ..schemas import EmailConfigCreate, EmailConfigUpdate, EmailConfigOut
from ..services.email_monitor import check_email_for_resumes

router = APIRouter(prefix="/email-config", tags=["邮箱配置"])


@router.get("", response_model=list[EmailConfigOut])
def list_configs(db: Session = Depends(get_db)):
    return db.query(EmailConfig).all()


@router.post("", response_model=EmailConfigOut)
def create_config(data: EmailConfigCreate, db: Session = Depends(get_db)):
    config = EmailConfig(**data.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put("/{config_id}", response_model=EmailConfigOut)
def update_config(config_id: int, data: EmailConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(EmailConfig).get(config_id)
    if not config:
        raise HTTPException(404, "配置不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(config, key, val)
    db.commit()
    db.refresh(config)
    return config


@router.delete("/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(EmailConfig).get(config_id)
    if not config:
        raise HTTPException(404, "配置不存在")
    db.delete(config)
    db.commit()
    return {"message": "已删除"}


@router.post("/test/{config_id}")
def test_email(config_id: int, db: Session = Depends(get_db)):
    """手动触发一次邮件检查"""
    config = db.query(EmailConfig).get(config_id)
    if not config:
        raise HTTPException(404, "配置不存在")
    try:
        results = check_email_for_resumes(db)
        return {"message": f"检查完成，导入 {len(results)} 份简历", "results": results}
    except Exception as e:
        raise HTTPException(500, f"邮箱连接失败: {str(e)}")


@router.post("/check-now")
def check_now(db: Session = Depends(get_db)):
    """立即检查所有活跃邮箱"""
    results = check_email_for_resumes(db)
    return {"message": f"检查完成，导入 {len(results)} 份简历", "results": results}
