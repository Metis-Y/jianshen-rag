"""用户与偏好数据访问。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Preference, User


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_preference(db: Session, user_id: int) -> Preference | None:
    return db.get(Preference, user_id)