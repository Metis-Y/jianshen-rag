"""文档数据访问。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Document


def find_dedup(db: Session, user_id: int, file_md5: str) -> Document | None:
    """同用户同 MD5 且 READY 的文档（上传秒传判定）。"""
    return db.scalar(
        select(Document).where(
            Document.user_id == user_id,
            Document.file_md5 == file_md5,
            Document.status == "READY",
        )
    )


def get(db: Session, doc_id: int) -> Document | None:
    return db.get(Document, doc_id)


def page(db: Session, user_id: int, category: str | None, page: int, size: int) -> tuple[int, list]:
    """分页列表：返回 (total, rows)。"""
    base = select(Document).where(Document.user_id == user_id)
    total = (
        db.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        or 0
    )
    stmt = base
    if category:
        stmt = stmt.where(Document.category == category)
    rows = db.scalars(
        stmt.order_by(Document.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return total, rows