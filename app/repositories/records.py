"""训练/体征/饮食记录数据访问 + 容量口径。"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import BodyMetric, DietLog, WorkoutLog


def exercise_volume(exercises: list) -> float:
    """容量 = Σ weight×sets×reps；三项缺一（快速模式）的动作不参与统计。"""
    total = 0.0
    for item in exercises or []:
        weight, sets, reps = item.get("weight"), item.get("sets"), item.get("reps")
        if weight is None or sets is None or reps is None:
            continue
        total += float(weight) * int(sets) * int(reps)
    return total


def workout_rows(
    db: Session, user_id: int, start: date | None = None, end: date | None = None
) -> list[WorkoutLog]:
    stmt = select(WorkoutLog).where(WorkoutLog.user_id == user_id)
    if start is not None:
        stmt = stmt.where(WorkoutLog.date >= start)
    if end is not None:
        stmt = stmt.where(WorkoutLog.date <= end)
    return db.scalars(stmt.order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc())).all()


def get_workout(db: Session, workout_id: int) -> WorkoutLog | None:
    return db.get(WorkoutLog, workout_id)


def any_workout(db: Session, user_id: int) -> bool:
    return (
        db.scalar(select(WorkoutLog.id).where(WorkoutLog.user_id == user_id).limit(1))
        is not None
    )


def recent_workouts(db: Session, user_id: int, limit: int = 3) -> list[WorkoutLog]:
    return db.scalars(
        select(WorkoutLog)
        .where(WorkoutLog.user_id == user_id)
        .order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc())
        .limit(limit)
    ).all()


def all_workouts(db: Session, user_id: int) -> list[WorkoutLog]:
    return db.scalars(select(WorkoutLog).where(WorkoutLog.user_id == user_id)).all()


def metric_rows(
    db: Session, user_id: int, start: date | None = None, end: date | None = None
) -> list[BodyMetric]:
    """有体重的体征序列（升序，供趋势计算）。"""
    stmt = select(BodyMetric).where(
        BodyMetric.user_id == user_id, BodyMetric.weight.is_not(None)
    )
    if start is not None:
        stmt = stmt.where(BodyMetric.date >= start)
    if end is not None:
        stmt = stmt.where(BodyMetric.date <= end)
    return db.scalars(stmt.order_by(BodyMetric.date.asc(), BodyMetric.id.asc())).all()


def any_metric(db: Session, user_id: int) -> bool:
    return (
        db.scalar(
            select(BodyMetric.id)
            .where(BodyMetric.user_id == user_id, BodyMetric.weight.is_not(None))
            .limit(1)
        )
        is not None
    )


def sleep_rows_since(db: Session, user_id: int, since: date) -> list[BodyMetric]:
    return db.scalars(
        select(BodyMetric).where(
            BodyMetric.user_id == user_id,
            BodyMetric.sleep_hours.is_not(None),
            BodyMetric.date >= since,
        )
    ).all()


def latest_soreness_metric(db: Session, user_id: int) -> BodyMetric | None:
    return db.scalar(
        select(BodyMetric)
        .where(BodyMetric.user_id == user_id, BodyMetric.soreness.is_not(None))
        .order_by(BodyMetric.date.desc(), BodyMetric.id.desc())
        .limit(1)
    )


def diet_rows(
    db: Session, user_id: int, start: date | None = None, end: date | None = None
) -> list[DietLog]:
    stmt = select(DietLog).where(DietLog.user_id == user_id)
    if start is not None:
        stmt = stmt.where(DietLog.date >= start)
    if end is not None:
        stmt = stmt.where(DietLog.date <= end)
    return db.scalars(stmt.order_by(DietLog.date.desc(), DietLog.id.desc())).all()


def get_diet(db: Session, diet_id: int) -> DietLog | None:
    return db.get(DietLog, diet_id)