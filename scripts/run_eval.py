"""M4 检索评估：对 tests/eval_set.json 的题库跑纯向量检索，输出命中率报告。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/run_eval.py

- 只测检索、不调对话模型；需要 embedding 网络
- 以 demo 账号的可见范围（个人文档 + 公共知识库）检索
- 输出：top1/top3/top5 命中率、MRR、按 tag 分组、top5 未命中清单、
  top5 里不同文档数（衡量"同一文档多切片挤占引用位"）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.repositories import users  # noqa: E402
from app.services import index  # noqa: E402

EVAL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "eval_set.json")
DEMO_USER = "demo"
TOPK = 5


def pct(n: int, total: int) -> str:
    return f"{n}/{total} = {n / total:.0%}" if total else "0/0"


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

    hits_1 = hits_3 = hits_5 = 0
    rr_sum = 0.0
    distinct_sum = 0
    misses: list[dict] = []
    by_tag: dict[str, dict] = {}

    for item in items:
        tag = item.get("tag", "未分类")
        stat = by_tag.setdefault(tag, {"total": 0, "hit5": 0, "hit3": 0, "hit1": 0})
        stat["total"] += 1

        try:
            results = index.retrieve(user_id, item["question"], top_k=TOPK)
        except Exception:  # embedding 抖动等：重试一次
            results = index.retrieve(user_id, item["question"], top_k=TOPK)

        titles = [r["doc_title"] for r in results]
        distinct_sum += len(set(titles))
        # expectDocs：同一知识点在语料中确有多处出处时，命中任一即可
        expects = item.get("expectDocs") or [item["expectDoc"]]
        ranks = [titles.index(e) + 1 for e in expects if e in titles]
        hit5 = bool(ranks)
        hit3 = bool(ranks) and min(ranks) <= 3
        hit1 = titles[0] in expects if titles else False
        if hit5:
            stat["hit5"] += 1
            hits_5 += 1
            rr_sum += 1.0 / min(ranks)
        if hit3:
            stat["hit3"] += 1
            hits_3 += 1
        if hit1:
            stat["hit1"] += 1
            hits_1 += 1
        if not hit5:
            misses.append({"question": item["question"], "expect": " / ".join(expects),
                           "got": titles, "tag": tag})

    total = len(items)
    print(f"题库 {total} 题（top{TOPK}，demo 可见语料）")
    print(f"top1 命中率：{pct(hits_1, total)}")
    print(f"top3 命中率：{pct(hits_3, total)}")
    print(f"top5 命中率：{pct(hits_5, total)}")
    print(f"MRR（越高越好，1.0 = 全部排第一）：{rr_sum / total:.3f}")
    print(f"top{TOPK} 平均不同文档数：{distinct_sum / total:.2f}（满分 {TOPK}）")

    print("\n按题型：")
    for tag, stat in by_tag.items():
        print(f"  [{tag}] top5 {pct(stat['hit5'], stat['total'])}"
              f"  | top3 {stat['hit3']}/{stat['total']}"
              f"  | top1 {stat['hit1']}/{stat['total']}")

    print(f"\ntop{TOPK} 未命中 {len(misses)} 题：")
    for m in misses:
        print(f"  [{m['tag']}] {m['question']}")
        print(f"        期望：{m['expect']}")
        print(f"        实际命中：{m['got']}")
    print()


if __name__ == "__main__":
    main()
