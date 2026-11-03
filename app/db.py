"""SQLAlchemy：引擎、会话、模型。一期启动时建表（简化）。"""
import os
import datetime as dt
from datetime import datetime

from sqlalchemy import JSON, Text, create_engine, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app import config

os.makedirs(os.path.dirname(config.SQLITE_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{config.SQLITE_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Preference(Base):
    """用户长期档案：目标 + 忌口。一人一行。"""

    __tablename__ = "preference"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    goal: Mapped[str | None] = mapped_column(String(32), default=None)   # 减脂/增肌/维持
    allergies: Mapped[list] = mapped_column(JSON, default=list)          # ["牛奶", ...]
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


class Document(Base):
    """训练计划/营养资料等文档（状态机：PROCESSING → READY / FAILED）。"""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_md5: Mapped[str] = mapped_column(String(32), index=True)
    size_bytes: Mapped[int] = mapped_column(default=0)
    category: Mapped[str] = mapped_column(String(16), default="other")   # plan / diet / other
    status: Mapped[str] = mapped_column(String(16), default="PROCESSING")
    fail_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


class WorkoutLog(Base):
    """一次训练记录：exercises 为 JSON 动作列表 [{"name","weight","sets","reps"}]，快速模式只填 name。"""

    __tablename__ = "workout_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    exercises: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(500), default=None)   # 感受
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class BodyMetric(Base):
    """体重/体脂等体征记录（body_fat/sleep_hours/soreness 预留，一期不参与统计）。"""

    __tablename__ = "body_metric"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    weight: Mapped[float | None] = mapped_column(default=None)
    body_fat: Mapped[float | None] = mapped_column(default=None)   # 预留
    sleep_hours: Mapped[float | None] = mapped_column(default=None)  # 预留（二期恢复线）
    soreness: Mapped[int | None] = mapped_column(default=None)      # 预留：1~5 酸痛度
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class DietLog(Base):
    """饮食记录：content 记吃了什么，avoid 为该次临时忌口/标签。"""

    __tablename__ = "diet_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    content: Mapped[str] = mapped_column(String(2000))
    avoid: Mapped[list | None] = mapped_column(JSON, default=None)   # ["牛奶", ...]
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Conversation(Base):
    """一次问答会话（D4）：title 取首次提问前 30 字。"""

    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Message(Base):
    """会话消息：role 为 user/assistant；assistant 消息携带 citations（引用数组 JSON）。"""

    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Feedback(Base):
    """回答反馈：is_positive 正/负评；user_id 冗余存储便于按用户统计正评率。"""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    is_positive: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()