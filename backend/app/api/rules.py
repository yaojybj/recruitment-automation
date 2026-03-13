from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ScreeningRule, Position
from ..schemas import ScreeningRuleCreate, ScreeningRuleUpdate, ScreeningRuleOut

router = APIRouter(prefix="/rules", tags=["筛选规则"])

AVAILABLE_FIELDS = [
    {"value": "education", "label": "学历", "type": "select",
     "options": ["博士", "硕士", "本科", "大专", "高中"]},
    {"value": "work_years", "label": "工作年限", "type": "number"},
    {"value": "age", "label": "年龄", "type": "number"},
    {"value": "city", "label": "城市", "type": "text"},
    {"value": "school", "label": "学校", "type": "text"},
    {"value": "major", "label": "专业", "type": "text"},
    {"value": "skills", "label": "技能", "type": "text"},
    {"value": "gender", "label": "性别", "type": "select", "options": ["男", "女"]},
    {"value": "expected_salary_max", "label": "期望薪资上限", "type": "number"},
    {"value": "current_company", "label": "当前公司", "type": "text"},
    {"value": "current_position", "label": "当前职位", "type": "text"},
    {"value": "raw_text", "label": "简历全文", "type": "text"},
]

AVAILABLE_OPERATORS = [
    {"value": "equals", "label": "等于"},
    {"value": "not_equals", "label": "不等于"},
    {"value": "contains", "label": "包含"},
    {"value": "not_contains", "label": "不包含"},
    {"value": "greater_than", "label": "大于"},
    {"value": "less_than", "label": "小于"},
    {"value": "greater_equal", "label": "大于等于"},
    {"value": "less_equal", "label": "小于等于"},
    {"value": "in", "label": "在列表中"},
    {"value": "not_in", "label": "不在列表中"},
    {"value": "regex", "label": "正则匹配"},
]


@router.get("/meta")
def get_rule_meta():
    return {"fields": AVAILABLE_FIELDS, "operators": AVAILABLE_OPERATORS}


@router.get("", response_model=list[ScreeningRuleOut])
def list_rules(position_id: int = None, db: Session = Depends(get_db)):
    query = db.query(ScreeningRule)
    if position_id:
        query = query.filter(ScreeningRule.position_id == position_id)
    return query.order_by(ScreeningRule.position_id, ScreeningRule.order).all()


@router.get("/{rule_id}", response_model=ScreeningRuleOut)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ScreeningRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    return rule


@router.post("", response_model=ScreeningRuleOut)
def create_rule(data: ScreeningRuleCreate, db: Session = Depends(get_db)):
    position = db.query(Position).get(data.position_id)
    if not position:
        raise HTTPException(404, "岗位不存在")
    rule = ScreeningRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=ScreeningRuleOut)
def update_rule(rule_id: int, data: ScreeningRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(ScreeningRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, val)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ScreeningRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    db.delete(rule)
    db.commit()
    return {"message": "已删除"}


@router.post("/batch")
def batch_create_rules(rules: list[ScreeningRuleCreate], db: Session = Depends(get_db)):
    created = []
    for data in rules:
        rule = ScreeningRule(**data.model_dump())
        db.add(rule)
        created.append(rule)
    db.commit()
    return {"message": f"创建了 {len(created)} 条规则"}
