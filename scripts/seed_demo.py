"""演示数据种子：创建 demo 账号，写入记录与偏好，导入三份示例资料。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/seed_demo.py

- 账号：demo / demo1234（已存在则复用）
- 记录类数据（训练/体征/饮食）每次执行会重置为本脚本内容
- 资料复用上传同款链路（解析→切分→向量索引），MD5 相同命中秒传不重复入库
"""
import io
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import UploadFile  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db import (  # noqa: E402
    BodyMetric,
    DietLog,
    Preference,
    SessionLocal,
    User,
    WorkoutLog,
)
from app.routers.auth import _hash  # noqa: E402
from app.services import document_service  # noqa: E402

SAMPLES = [
    ("训练计划示例.md", "plan"),
    ("减脂饮食示例.md", "diet"),
    ("动作要点示例.md", "plan"),
]

# 三天训练：固定动作与重量，容量可手工核算（深蹲 80×5×5=2000 …）
WORKOUTS = [
    (-6, [
        {"name": "深蹲", "weight": 80, "sets": 5, "reps": 5},
        {"name": "卧推", "weight": 50, "sets": 5, "reps": 5},
        {"name": "杠铃划船", "weight": 60, "sets": 8, "reps": 3},
    ]),
    (-3, [
        {"name": "硬拉", "weight": 100, "sets": 5, "reps": 3},
        {"name": "站姿推举", "weight": 40, "sets": 8, "reps": 3},
        {"name": "引体向上"},  # 快速模式：只记动作名
    ]),
    (0, [
        {"name": "深蹲", "weight": 82.5, "sets": 5, "reps": 5},
        {"name": "卧推", "weight": 52.5, "sets": 5, "reps": 5},
        {"name": "杠铃划船", "weight": 62.5, "sets": 8, "reps": 3},
    ]),
]

METRICS = [
    (-6, 80.5, 22.1),
    (-3, 79.8, 21.6),
    (0, 79.2, 21.2),
]


def d(offset: int) -> date:
    return date.today() + timedelta(days=offset)


def volume(exercises: list) -> float:
    """容量 = Σ weight×sets×reps，与后端 exercise_volume 同口径。"""
    total = 0.0
    for item in exercises:
        if all(k in item for k in ("weight", "sets", "reps")):
            total += item["weight"] * item["sets"] * item["reps"]
    return total


def main() -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "demo"))
        if user is None:
            user = User(username="demo", password_hash=_hash("demo1234"))
            db.add(user)
            db.flush()
            print("已创建 demo 账号（demo / demo1234）")
        else:
            print("复用已有 demo 账号")

        pref = db.get(Preference, user.id)
        if pref is None:
            pref = Preference(user_id=user.id)
            db.add(pref)
        pref.goal = "减脂"
        pref.allergies = ["牛奶"]

        # 记录类数据重置为种子内容
        db.execute(delete(WorkoutLog).where(WorkoutLog.user_id == user.id))
        db.execute(delete(BodyMetric).where(BodyMetric.user_id == user.id))
        db.execute(delete(DietLog).where(DietLog.user_id == user.id))
        for offset, exercises in WORKOUTS:
            db.add(WorkoutLog(user_id=user.id, date=d(offset), exercises=exercises))
        for offset, weight, body_fat in METRICS:
            db.add(BodyMetric(user_id=user.id, date=d(offset), weight=weight, body_fat=body_fat))
        db.add(DietLog(
            user_id=user.id,
            date=d(0),
            content="午餐：鸡胸肉蔬菜沙拉（无酱）；晚餐：清蒸鲈鱼 + 清炒西兰花；加餐：苹果一个",
        ))
        db.commit()

        week_volume = sum(volume(ex) for _, ex in WORKOUTS)
        weight_delta = round(METRICS[-1][1] - METRICS[0][1], 1)
        print(f"已写入：3 天训练（近 7 天总容量 {week_volume:g}kg）、3 条体重"
              f"（{METRICS[0][1]}→{METRICS[-1][1]}kg，变化 {weight_delta}kg）、"
              "1 条饮食、偏好（减脂 / 忌口牛奶）")

        # 示例资料：复用上传链路（解析→切分→向量索引），重复执行命中秒传
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name, category in SAMPLES:
            path = os.path.join(root, "samples", name)
            with open(path, "rb") as f:
                content = f.read()
            upload = UploadFile(file=io.BytesIO(content), filename=name)
            data = document_service.create_document(db, user, upload, category)
            print(f"资料 {name}: status={data['status']} "
                  f"chunks={data['chunkCount']} dedup={data['dedup']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()