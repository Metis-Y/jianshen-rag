"""会话/消息/反馈与统计查询。"""
from datetime import date, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db import BodyMetric, Conversation, Document, Feedback, Message, WorkoutLog
from app.repositories.records import exercise_volume


def conversations_page(db: Session, user_id: int, page: int, size: int) -> tuple[int, list]:
    """会话分页：返回 (total, rows)。"""
    total = (
        db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
        )
        or 0
    )
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return total, rows


def get_conversation(db: Session, conv_id: int) -> Conversation | None:
    return db.get(Conversation, conv_id)


def get_message(db: Session, message_id: int) -> Message | None:
    return db.get(Message, message_id)


def message_ids(db: Session, conv_id: int) -> list[int]:
    return list(db.scalars(select(Message.id).where(Message.conversation_id == conv_id)).all())


def messages_with_feedback(db: Session, conv_id: int, user_id: int) -> tuple[list, dict]:
    """会话消息（升序）+ 当前用户对各消息的反馈 {message_id: bool}。"""
    rows = db.scalars(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.id.asc())
    ).all()
    fb_map: dict[int, bool] = {}
    if rows:
        fbs = db.scalars(
            select(Feedback).where(
                Feedback.message_id.in_([m.id for m in rows]),
                Feedback.user_id == user_id,
            )
        ).all()
        fb_map = {fb.message_id: fb.is_positive for fb in fbs}
    return rows, fb_map


def get_feedback(db: Session, user_id: int, message_id: int) -> Feedback | None:
    return db.scalar(
        select(Feedback).where(
            Feedback.message_id == message_id, Feedback.user_id == user_id
        )
    )


def _fmt_volume(value: float | int) -> int | float:
    """整数容量输出 int，非整数保留 float（对齐 /workouts 输出风格）。"""
    if isinstance(value, int):
        return value
    return int(value) if value.is_integer() else value


def stats(db: Session, user_id: int) -> dict:
    """首页统计六项，全部按用户过滤。"""
    doc_count = (
        db.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        or 0
    )
    log_days = (
        db.scalar(
            select(func.count(distinct(WorkoutLog.date))).where(WorkoutLog.user_id == user_id)
        )
        or 0
    )
    qa_count = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id, Message.role == "assistant")
        )
        or 0
    )
    fb_positive = (
        db.scalar(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.user_id == user_id, Feedback.is_positive.is_(True))
        )
        or 0
    )
    fb_total = (
        db.scalar(select(func.count()).select_from(Feedback).where(Feedback.user_id == user_id))
        or 0
    )
    positive_rate = round(fb_positive / fb_total, 2) if fb_total else None

    latest = db.scalar(
        select(BodyMetric)
        .where(BodyMetric.user_id == user_id, BodyMetric.weight.is_not(None))
        .order_by(BodyMetric.date.desc(), BodyMetric.id.desc())
        .limit(1)
    )
    week_since = date.today() - timedelta(days=6)
    week_rows = db.scalars(
        select(WorkoutLog).where(
            WorkoutLog.user_id == user_id, WorkoutLog.date >= week_since
        )
    ).all()
    week_volume = _fmt_volume(sum(exercise_volume(w.exercises) for w in week_rows))

    return {
        "docCount": doc_count,
        "logDays": log_days,
        "qaCount": qa_count,
        "positiveRate": positive_rate,
        "latestWeight": latest.weight if latest else None,
        "weekVolume": week_volume,
    }