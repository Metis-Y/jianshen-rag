"""请求/响应模型（docs/05 契约的载体）。"""
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)


class LoginIn(RegisterIn):
    pass


class TokenOut(BaseModel):
    token: str
    exp: int


class UserOut(BaseModel):
    id: int
    username: str


class MeOut(BaseModel):
    id: int
    username: str
    goal: str | None = None
    allergies: list = []