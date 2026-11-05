"""演示数据种子：demo 账号 + 记录偏好 + 个人示例资料 + 公共知识库。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/seed_demo.py

- 账号：demo / demo1234（已存在则复用）
- 记录类数据（训练/体征/饮食）每次执行会重置为本脚本内容
- 个人资料复用上传同款链路（解析→切分→向量索引），MD5 相同命中秒传不重复入库
- 公共知识库：samples/public/ 由 system 账号持有，全体用户可检索；每次执行重建
- 收尾对全部 READY 文档做一次向量元数据归一（补齐 is_public 字段）
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
    Document,
    Preference,
    SessionLocal,
    User,
    WorkoutLog,
)
from app.routers.auth import _hash  # noqa: E402
from app.services import document_service, index, pipeline  # noqa: E402
from scripts.corpus_manifest import PUBLIC_CORPUS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLES = [
    ("训练计划示例.md", "plan"),
    ("减脂饮食示例.md", "diet"),
    ("动作要点示例.md", "plan"),
]

# 公共语料清单统一放在 scripts/corpus_manifest.py（见 PUBLIC_CORPUS 导入）

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
    (-6, 80.5, 22.1, 7.5, 3),
    (-3, 79.8, 21.6, 7.0, 2),
    (0, 79.2, 21.2, 8.5, 1),
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


def _upload_to(db, user, folder: str, samples: list, is_public: bool) -> None:
    for name, category in samples:
        path = os.path.join(ROOT, "samples", folder, name)
        with open(path, "rb") as f:
            content = f.read()
        upload = UploadFile(file=io.BytesIO(content), filename=name)
        data = document_service.create_document(db, user, upload, category, is_public=is_public)
        tag = "公共资料" if is_public else "资料"
        print(f"{tag} {name}: status={data['status']} "
              f"chunks={data['chunkCount']} dedup={data['dedup']}")


def main() -> None:
    db = SessionLocal()
    try:
        # ---- 1. demo 账号与记录 ----
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
        pref.targets = {"weight": 78.0, "strength": [{"name": "深蹲", "value": 90.0}]}

        db.execute(delete(WorkoutLog).where(WorkoutLog.user_id == user.id))
        db.execute(delete(BodyMetric).where(BodyMetric.user_id == user.id))
        db.execute(delete(DietLog).where(DietLog.user_id == user.id))
        for offset, exercises in WORKOUTS:
            db.add(WorkoutLog(user_id=user.id, date=d(offset), exercises=exercises))
        for offset, weight, body_fat, sleep_hours, soreness in METRICS:
            db.add(BodyMetric(
                user_id=user.id, date=d(offset), weight=weight,
                body_fat=body_fat, sleep_hours=sleep_hours, soreness=soreness,
            ))
        db.add(DietLog(
            user_id=user.id,
            date=d(0),
            meal="午餐",
            content="午餐：鸡胸肉蔬菜沙拉（无酱）；晚餐：清蒸鲈鱼 + 清炒西兰花；加餐：苹果一个",
        ))
        db.commit()

        week_volume = sum(volume(ex) for _, ex in WORKOUTS)
        weight_delta = round(METRICS[-1][1] - METRICS[0][1], 1)
        print(f"已写入：3 天训练（近 7 天总容量 {week_volume:g}kg）、3 条体重"
              f"（{METRICS[0][1]}→{METRICS[-1][1]}kg，变化 {weight_delta}kg）、"
              "1 条饮食、偏好（减脂 / 忌口牛奶）")

        # ---- 2. demo 个人示例资料 ----
        _upload_to(db, user, ".", SAMPLES, is_public=False)

        # ---- 3. 公共知识库（system 持有，全体用户可检索）----
        sys_user = db.scalar(select(User).where(User.username == "system"))
        if sys_user is None:
            sys_user = User(username="system", password_hash=_hash(os.urandom(6).hex()))
            db.add(sys_user)
            db.flush()
            print("已创建 system 账号（公共知识库归属）")

        old_public = db.scalars(
            select(Document).where(Document.user_id == sys_user.id)
        ).all()
        for doc in old_public:
            document_service.delete_document(db, sys_user, doc.id)
        if old_public:
            print(f"已清理公共知识库旧资料 {len(old_public)} 份")
        _upload_to(db, sys_user, "public", PUBLIC_CORPUS, is_public=True)

        # ---- 4. 向量元数据归一：为存量文档补齐 is_public 字段 ----
        ready_docs = db.scalars(select(Document).where(Document.status == "READY")).all()
        for doc in ready_docs:
            data = pipeline.load_chunks(doc.id)
            index.remove_document(doc.id)
            index.index_document(
                doc.id,
                doc.filename,
                doc.user_id,
                doc.category,
                data["chunks"],
                is_public=bool(doc.is_public),
            )
        print(f"已归一化 {len(ready_docs)} 份文档的向量元数据")
    finally:
        db.close()


if __name__ == "__main__":
    main()