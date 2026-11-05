"""问答聚合（双块 Prompt 的【我的数据】来源）：只给真实小数字，杜绝编造。"""
import datetime as dt

from sqlalchemy.orm import Session

from app.repositories import records, users


def fmt_num(value: float) -> int | float:
    """12000.0 → 12000；1812.5 保留一位。"""
    v = float(value)
    return int(v) if v.is_integer() else round(v, 1)


def summarize(db: Session, user_id: int) -> dict:
    """聚合用户真实数据：容量/体重/恢复/目标进度，返回快照字典。"""
    since30 = dt.date.today() - dt.timedelta(days=29)
    since7 = dt.date.today() - dt.timedelta(days=6)

    workouts30 = records.workout_rows(db, user_id, start=since30)
    volume30 = sum(records.exercise_volume(w.exercises) for w in workouts30)
    has_any_workout = records.any_workout(db, user_id)

    metrics30 = records.metric_rows(db, user_id, start=since30)
    has_any_metric = records.any_metric(db, user_id)
    latest_weight = metrics30[-1].weight if metrics30 else None
    weight_delta: float | None = None
    if len(metrics30) > 1:
        weight_delta = round(metrics30[-1].weight - metrics30[0].weight, 1)
    elif len(metrics30) == 1:
        weight_delta = 0

    sleep_rows = records.sleep_rows_since(db, user_id, since7)
    avg_sleep = (
        round(sum(m.sleep_hours for m in sleep_rows) / len(sleep_rows), 1)
        if sleep_rows else None
    )
    latest_sore = records.latest_soreness_metric(db, user_id)
    latest_soreness = latest_sore.soreness if latest_sore else None

    pref = users.get_preference(db, user_id)
    targets = (pref.targets or {}) if pref else {}

    recent = records.recent_workouts(db, user_id, limit=3)
    recent_sessions = [
        f"{w.date.month}-{w.date.day}：{fmt_num(records.exercise_volume(w.exercises))}kg"
        for w in reversed(recent)
    ]

    # 力量目标进度：每条目标按动作名匹配最好成绩（兼容旧单目标/squat 格式）
    strength_goals = targets.get("strength") or []
    if isinstance(strength_goals, dict):
        strength_goals = [strength_goals]
    if not strength_goals and targets.get("squat") is not None:
        strength_goals = [{"name": "深蹲", "value": targets.get("squat")}]
    if not strength_goals:
        strength_goals = [{"name": "深蹲", "value": None}]  # 无目标时仅展示最好成绩
    goal_progress: list[dict] = []
    all_rows = records.all_workouts(db, user_id)
    for g in strength_goals:
        name = (str(g.get("name") or "深蹲")).strip() or "深蹲"
        value = g.get("value")
        mx: float | None = None
        for w in all_rows:
            for ex in w.exercises or []:
                if (
                    isinstance(ex, dict)
                    and name in str(ex.get("name", ""))
                    and ex.get("weight") is not None
                ):
                    mx = max(mx or 0.0, float(ex["weight"]))
        goal_progress.append({"name": name, "value": value, "max": mx})

    return {
        "volume30": volume30,
        "recent_sessions": recent_sessions,
        "has_any_workout": has_any_workout,
        "latest_weight": latest_weight,
        "weight_delta": weight_delta,
        "has_any_metric": has_any_metric,
        "goal": pref.goal if pref else None,
        "allergies": pref.allergies if pref and pref.allergies else [],
        "avg_sleep": avg_sleep,
        "latest_soreness": latest_soreness,
        "target_weight": targets.get("weight"),
        "goal_progress": goal_progress,
    }