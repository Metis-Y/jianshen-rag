"""训练记录路由（docs/API.md 第 4 节契约）。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import User, WorkoutLog, get_db
from app.schemas import WorkoutIn

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


def parse_date_range(from_: str | None, to_: str | None) -> tuple[date | None, date | None]:
    """解析可选区间参数（含边界）；格式非法或 from 晚于 to 时 400。"""
    parsed: dict[str, date] = {}
    for field, raw in (("from", from_), ("to", to_)):
        if raw is None:
            continue
        try:
            parsed[field] = date.fromisoformat(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{field} 参数格式非法，应为 YYYY-MM-DD") from None
    start, end = parsed.get("from"), parsed.get("to")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=400, detail="from 不能晚于 to")
    return start, end


def exercise_volume(exercises: list) -> float:
    """容量 = Σ weight×sets×reps；三项缺一（快速模式）的动作不参与统计但保留记录。"""
    total = 0.0
    for item in exercises or []:
        weight, sets, reps = item.get("weight"), item.get("sets"), item.get("reps")
        if weight is None or sets is None or reps is None:
            continue
        total += float(weight) * int(sets) * int(reps)
    return total


def _fmt_num(value: float | int) -> int | float:
    """整数容量输出 int（如 3500），非整数保留 float（如 1812.5）。空集会得到 int 0，须兼容。"""
    if isinstance(value, int):
        return value
    return int(value) if value.is_integer() else value


def _record_out(log: WorkoutLog) -> dict:
    return {
        "id": log.id,
        "date": log.date.isoformat(),
        "volume": _fmt_num(exercise_volume(log.exercises)),
        "exercises": log.exercises,
        "note": log.note,
    }


@router.post("")
def create(
    body: WorkoutIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log = WorkoutLog(
        user_id=user.id,
        date=body.date,
        exercises=[item.model_dump(exclude_none=True) for item in body.exercises],
        note=body.note,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return resp.ok({"id": log.id, "volume": _fmt_num(exercise_volume(log.exercises))})


@router.get("")
def list_workouts(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = parse_date_range(from_, to)
    stmt = select(WorkoutLog).where(WorkoutLog.user_id == user.id)
    if start is not None:
        stmt = stmt.where(WorkoutLog.date >= start)
    if end is not None:
        stmt = stmt.where(WorkoutLog.date <= end)
    stmt = stmt.order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc())
    records = [_record_out(row) for row in db.scalars(stmt).all()]
    total = _fmt_num(sum(record["volume"] for record in records))
    return resp.ok({"totalVolume": total, "records": records})