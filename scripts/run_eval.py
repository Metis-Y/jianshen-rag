"""M4 检索评估：对 tests/eval_set.json 的题库跑纯向量检索，输出命中率报告。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/run_eval.py

- 只测检索、不调对话模型；需要 embedding 网络
- 以 demo 账号的可见范围（个人文档 + 公共知识库）检索
- 输出：总体 top5/top1 命中率、按 tag 分组、未命中清单
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, User  # noqa: E402
from app.repositories import users  # noqa: E402
from app.services import index  # noqa: E402

EVAL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "eval_set.json")
DEMO_USER = "demo"
TOP_K = 5


def main() -> None:
    with open(EVAL_PATH, encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]

    db = SessionLocal()
    try:
        user = users.get_by_username(db, DEMO_USER)
        if user is None:
            sys.exit("demo 账号不存在，先跑 scripts/seed_demo.py")
        user_id = user.id
    finally:
        db.close()

    hits_1 = hits_5 = 0
    rank_sum = 0
    rank_n = 0
    misses: list[dict] = []
    by_tag: dict[str, dict] = {}

    for item in items:
        tag = item.get("tag", "未分类")
        stat = by_tag.setdefault(tag, {"total": 0, "hit5": 0, "hit1": 0})
        stat["total"] += 1

        try:
            results = index.retrieve(user_id, item["question"], top_k=TOP_K)
        except Exception as exc:  # embedding 抖动等：重试一次
            results = index.retrieve(user_id, item["question"], top_k=TOP_K)

        titles = [r["doc_title"] for r in results]
        expect = item["expectDoc"]
        hit5 = expect in titles
        hit1 = titles[0] == expect if titles else False
        if hit5:
            stat["hit5"] += 1
            hits_5 += 1
            rank = titles.index(expect) + 1
            rank_sum += rank
            rank_n += 1
        if hit1:
            stat["hit1"] += 1
            hits_1 += 1
        else:
            misses.append({"question": item["question"], "expect": expect,
                           "got": titles[:3], "tag": tag})

    total = len(items)
    print(f"题库 {total} 题（top{TOP_K}，demo 可见语料）")
    print(f"top1 命中率：{hits_1}/{total} = {hits_1 / total:.0%}")
    print(f"top5 命中率：{hits_5}/{total} = {hits_5 / total:.0%}")
    if rank_n:
        print(f"命中的平均排名：{rank_sum / rank_n:.2f}")

    print("\n按题型：")
    for tag, stat in by_tag.items():
        print(f"  [{tag}] top5 {stat['hit5']}/{stat['total']} = {stat['hit5'] / stat['total']:.0%}"
              f"  | top1 {stat['hit1']}/{stat['total']}")

    print(f"\n未命中 {len(misses)} 题：")
    for m in misses:
        print(f"  [{m['tag']}] {m['question']}")
        print(f"        期望：{m['expect']}")
        print(f"        实际命中：{m['got']}")
    print()


if __name__ == "__main__":
    main()