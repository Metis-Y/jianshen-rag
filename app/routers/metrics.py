"""体征记录路由（docs/API.md 第 4 节契约）：最新值 + 序列 + 首末变化量。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import BodyMetric, User, get_db
from app.repositories import records as records_repo
from app.routers.workouts import parse_date_range
from app.schemas import MetricIn

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.post("")
def create(
    body: MetricIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = BodyMetric(
        user_id=user.id,
        date=body.date,
        weight=body.weight,
        body_fat=body.body_fat,
        sleep_hours=body.sleep_hours,
        soreness=body.soreness,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return resp.ok({"id": row.id})


@router.get("")
def list_metrics(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = parse_date_range(from_, to)
    span = records_repo.metric_rows(db, user.id, start, end)
    series = [
        {
            "date": row.date.isoformat(),
            "weight": row.weight,
            "sleepHours": row.sleep_hours,
            "soreness": row.soreness,
        }
        for row in span
    ]
    if not series:
        return resp.ok({"latest": None, "delta": None, "series": []})
    # delta = 末次 - 首次；单条记录时为 0
    delta = series[-1]["weight"] - series[0]["weight"] if len(series) > 1 else 0
    return resp.ok({"latest": series[-1], "delta": round(delta, 1), "series": series})