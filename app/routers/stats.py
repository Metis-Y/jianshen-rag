"""统计接口（docs/API.md 第 6 节契约）：查询已下沉 repositories/chat.stats。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import User, get_db
from app.repositories import chat as chat_repo

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resp.ok(chat_repo.stats(db, user.id))