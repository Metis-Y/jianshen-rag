"""请求/响应模型（docs/05 契约的载体）。"""
import datetime

from pydantic import BaseModel, ConfigDict, Field


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


# ---------- 记录：训练 / 体征 / 饮食 ----------


class ExerciseIn(BaseModel):
    """单个动作：name 必填；weight/sets/reps 可选正整数，三项齐全才计入容量。"""

    name: str = Field(min_length=1, max_length=100)
    weight: float | None = Field(default=None, gt=0)
    sets: int | None = Field(default=None, ge=1)
    reps: int | None = Field(default=None, ge=1)


class WorkoutIn(BaseModel):
    date: datetime.date
    exercises: list[ExerciseIn] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)


class MetricIn(BaseModel):
    """bodyFat/sleepHours/soreness 预留，一期可不传。"""

    model_config = ConfigDict(populate_by_name=True)

    date: datetime.date
    weight: float = Field(gt=0)
    body_fat: float | None = Field(default=None, gt=0, alias="bodyFat")
    sleep_hours: float | None = Field(default=None, ge=0, alias="sleepHours")
    soreness: int | None = Field(default=None, ge=1, le=5)


class DietIn(BaseModel):
    date: datetime.date
    meal: str | None = Field(default=None, max_length=16)   # 早餐/午餐/晚餐（可选）
    content: str = Field(min_length=1, max_length=2000)
    avoid: list[str] | None = None   # 历史兼容字段，前端表单已不提交


class PreferenceIn(BaseModel):
    """PUT 整体覆盖：字段均可选，缺省即清空。
    目标里程碑：targetWeight 目标体重；targetStrengthName/targetStrengthValue 目标力量（动作自选）。"""

    model_config = ConfigDict(populate_by_name=True)

    goal: str | None = Field(default=None, max_length=32)
    allergies: list[str] | None = None
    target_weight: float | None = Field(default=None, gt=0, alias="targetWeight")
    target_strength_name: str | None = Field(default=None, max_length=16, alias="targetStrengthName")
    target_strength_value: float | None = Field(default=None, gt=0, alias="targetStrengthValue")


# ---------- 问答（docs/API.md 第 5、6 节） ----------


class ChatIn(BaseModel):
    """POST /api/chat：documentIds 限定检索范围；conversationId 不传则新建会话。"""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = Field(default=None, alias="conversationId")
    document_ids: list[int] | None = Field(default=None, alias="documentIds")


class FeedbackIn(BaseModel):
    """POST /api/messages/{id}/feedback 入参：true 有帮助 / false 没帮助 / null 取消。"""

    positive: bool | None = None