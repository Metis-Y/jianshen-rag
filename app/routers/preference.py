"""偏好路由（docs/API.md 第 2 节契约）：目标 + 长期忌口，一人一行，PUT 整体覆盖。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import Preference, User, get_db
from app.schemas import PreferenceIn

router = APIRouter(prefix="/api/preference", tags=["preference"])


def _pref_out(pref: Preference | None) -> dict:
    """未设置时：goal=null、allergies=[]、目标=null（兼容旧的 squat 格式）。"""
    if pref is None:
        return {
            "goal": None, "allergies": [],
            "targetWeight": None, "targetStrengthName": None, "targetStrengthValue": None,
        }
    t = pref.targets or {}
    strength = t.get("strength") or {}
    name = strength.get("name") or ("深蹲" if t.get("squat") is not None else None)
    value = strength.get("value") if strength.get("value") is not None else t.get("squat")
    return {
        "goal": pref.goal,
        "allergies": pref.allergies if pref.allergies else [],
        "targetWeight": t.get("weight"),
        "targetStrengthName": name,
        "targetStrengthValue": value,
    }


@router.get("")
def get_pref(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp.ok(_pref_out(db.get(Preference, user.id)))


@router.put("")
def put_pref(
    body: PreferenceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = db.get(Preference, user.id)
    if pref is None:  # 注册时已建行，此处兜底
        pref = Preference(user_id=user.id)
        db.add(pref)
    pref.goal = body.goal
    pref.allergies = body.allergies if body.allergies is not None else []
    if body.target_strength_value is not None or body.target_strength_name:
        name = (body.target_strength_name or "深蹲").strip() or "深蹲"
        strength = {"name": name, "value": body.target_strength_value}
    else:
        strength = None
    pref.targets = {"weight": body.target_weight, "strength": strength}
    db.commit()
    return resp.ok(_pref_out(pref))