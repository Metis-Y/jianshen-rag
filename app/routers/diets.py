"""饮食记录路由（docs/API.md 第 4 节契约）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import DietLog, User, get_db
from app.routers.workouts import parse_date_range
from app.schemas import DietIn

router = APIRouter(prefix="/api/diets", tags=["diets"])


def _record_out(row: DietLog) -> dict:
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "content": row.content,
        "avoid": row.avoid or [],
    }


@router.post("")
def create(
    body: DietIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = DietLog(user_id=user.id, date=body.date, content=body.content, avoid=body.avoid)
    db.add(row)
    db.commit()
    db.refresh(row)
    return resp.ok({"id": row.id})


@router.get("")
def list_diets(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = parse_date_range(from_, to)
    stmt = select(DietLog).where(DietLog.user_id == user.id)
    if start is not None:
        stmt = stmt.where(DietLog.date >= start)
    if end is not None:
        stmt = stmt.where(DietLog.date <= end)
    stmt = stmt.order_by(DietLog.date.desc(), DietLog.id.desc())
    return resp.ok({"records": [_record_out(row) for row in db.scalars(stmt).all()]})