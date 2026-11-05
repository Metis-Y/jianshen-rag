"""认证路由：注册 / 登录 / 当前用户。"""
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import resp
from app.auth import create_token, get_current_user
from app.db import Preference, User, get_db
from app.repositories import users
from app.schemas import LoginIn, MeOut, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    exists = users.get_by_username(db, body.username)
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=body.username, password_hash=_hash(body.password))
    db.add(user)
    db.flush()
    db.add(Preference(user_id=user.id))
    db.commit()
    return resp.ok(UserOut(id=user.id, username=user.username).model_dump())


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = users.get_by_username(db, body.username)
    if user is None or not _verify(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token, exp = create_token(user.id)
    return resp.ok(TokenOut(token=token, exp=exp).model_dump())


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = users.get_preference(db, user.id)
    data = MeOut(
        id=user.id,
        username=user.username,
        goal=pref.goal if pref else None,
        allergies=pref.allergies if pref else [],
    )
    return resp.ok(data.model_dump())