"""JWT 签发与校验依赖。"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import config
from app.db import User, get_db

_bearer = HTTPBearer(auto_error=False)


def create_token(user_id: int) -> tuple[str, int]:
    """签发 JWT，返回 (token, 过期时间戳秒)。"""
    exp = datetime.now(timezone.utc) + timedelta(hours=config.JWT_TTL_HOURS)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGO), int(exp.timestamp())


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未认证：缺少 token")
    try:
        payload = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGO])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user