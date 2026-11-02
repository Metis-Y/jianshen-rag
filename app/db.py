"""SQLAlchemy：引擎、会话、模型。一期启动时建表（简化）。"""
import os
from datetime import date, datetime

from sqlalchemy import JSON, create_engine, String
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()