"""统计接口（docs/API.md 第 6 节契约）：全部按当前用户过滤。"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import (
    BodyMetric,
    Conversation,
    Document,
    Feedback,
    Message,
    User,
    WorkoutLog,
    get_db,
)
from app.routers.workouts import exercise_volume  # 复用容量聚合公式

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _fmt_num(value: float | int) -> int | float:
    """整数容量输出 int，非整数保留 float（对齐 /workouts 的输出风格）。"""
    if isinstance(value, int):
        return value
    return int(value) if value.is_integer() else value


@router.get("")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc_count = (
        db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user.id)) or 0
    )
    log_days = (
        db.scalar(
            select(func.count(distinct(WorkoutLog.date))).where(WorkoutLog.user_id == user.id)
        )
        or 0
    )
    qa_count = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user.id, Message.role == "assistant")
        )
        or 0
    )
    fb_positive = (
        db.scalar(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.user_id == user.id, Feedback.is_positive.is_(True))
        )
        or 0
    )
    fb_total = (
        db.scalar(select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id)) or 0
    )
    positive_rate = round(fb_positive / fb_total, 2) if fb_total else None

    latest = db.scalar(
        select(BodyMetric)
        .where(BodyMetric.user_id == user.id, BodyMetric.weight.is_not(None))
        .order_by(BodyMetric.date.desc(), BodyMetric.id.desc())
        .limit(1)
    )

    week_since = date.today() - timedelta(days=6)  # 近 7 天（含今天）
    week_rows = db.scalars(
        select(WorkoutLog).where(WorkoutLog.user_id == user.id, WorkoutLog.date >= week_since)
    ).all()
    week_volume = _fmt_num(sum(exercise_volume(w.exercises) for w in week_rows))

    return resp.ok(
        {
            "docCount": doc_count,
            "logDays": log_days,
            "qaCount": qa_count,
            "positiveRate": positive_rate,
            "latestWeight": latest.weight if latest else None,
            "weekVolume": week_volume,
        }
    )