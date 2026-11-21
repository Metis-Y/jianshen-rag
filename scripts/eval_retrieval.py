"""M4 检索评估：对 docs/端到端题库.md 的题库跑纯向量检索，输出命中率报告。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/eval_retrieval.py

- 只测检索、不调对话模型；需要 embedding 网络
- 以 demo 账号的可见范围（个人文档 + 公共知识库）检索
- 输出：top1/top3/top5 命中率、MRR、按 tag 分组、top5 未命中清单、
  top5 里不同文档数（衡量"同一文档多切片挤占引用位"）
- 持久化：逐题 JSON + 人读 MD 落 results/，并进 MLflow（params/metrics/tags/artifact）；
  top5 / MRR 低于阈值只打印告警，不影响退出码
"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.repositories import users  # noqa: E402
from app.services import index  # noqa: E402
from scripts.eval_common import load_eval_set  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(ROOT, "docs", "端到端题库.md")
DEMO_USER = "demo"
TOPK = 5

# 告警阈值（只打印提醒，不改变退出码；上 CI 后再决定是否挂非零退出）
WARN_TOP5 = 0.9
WARN_MRR = 0.85


def pct(n: int, total: int) -> str:
    return f"{n}/{total} = {n / total:.0%}" if total else "0/0"


def main() -> None:
    items = load_eval_set(EVAL_PATH)

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
    detail: list[dict] = []

    for item in items:
        tag = item.get("tag", "未分类")
        stat = by_tag.setdefault(tag, {"total": 0, "hit5": 0, "hit3": 0, "hit1": 0})
        stat["total"] += 1

        t0 = time.perf_counter()
        try:
            results = index.retrieve(user_id, item["question"], top_k=TOPK, with_scores=True)
        except Exception:  # embedding 抖动等：重试一次
            results = index.retrieve(user_id, item["question"], top_k=TOPK, with_scores=True)
        latency_ms = round((time.perf_counter() - t0) * 1000)

        titles = [r["doc_title"] for r in results]
        distinct_sum += len(set(titles))
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
            misses.append({
                "question": item["question"],
                "expect": " / ".join(expects),
                "got": titles,
                "tag": tag,
            })

        detail.append({
            "question": item["question"],
            "tag": tag,
            "expect": " / ".join(expects),
            "got": titles,
            "best_rank": min(ranks) if ranks else None,
            "hit1": bool(hit1),
            "hit3": bool(hit3),
            "hit5": bool(hit5),
            "latency_ms": latency_ms,
            "top_scores": [
                {
                    "doc_title": r["doc_title"],
                    "distance": r.get("distance"),
                    "recall_rank": r.get("recall_rank"),
                    "rerank_score": r.get("rerank_score"),
                    "rerank_rank": r.get("rerank_rank"),
                }
                for r in results
            ],
        })

    total = len(items)
    top1_rate = hits_1 / total
    top3_rate = hits_3 / total
    top5_rate = hits_5 / total
    mrr = rr_sum / total
    avg_distinct = distinct_sum / total

    print(f"题库 {total} 题（top{TOPK}，demo 可见语料）")
    print(f"top1 命中率：{pct(hits_1, total)}")
    print(f"top3 命中率：{pct(hits_3, total)}")
    print(f"top5 命中率：{pct(hits_5, total)}")
    print(f"MRR（越高越好，1.0 = 全部排第一）：{mrr:.3f}")
    print(f"top{TOPK} 平均不同文档数：{avg_distinct:.2f}（满分 {TOPK}）")

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

    # ---- 持久化：逐题 JSON + 人读 MD ----
    res_dir = os.path.join(ROOT, "results")
    os.makedirs(res_dir, exist_ok=True)
    date = dt.date.today().isoformat()
    # 同一天多次跑：文件名用"第几次"编号，避免互相覆盖
    seq = 1
    for name in os.listdir(res_dir):
        if name.startswith(f"retrieval_{date}_") and name.endswith(".json"):
            seq += 1

    json_path = os.path.join(res_dir, f"retrieval_{date}_{seq}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date,
                "summary": {
                    "question_count": total,
                    "top1": round(top1_rate, 4),
                    "top3": round(top3_rate, 4),
                    "top5": round(top5_rate, 4),
                    "mrr": round(mrr, 4),
                    "avg_distinct_docs": round(avg_distinct, 4),
                    "miss_count": len(misses),
                },
                "by_tag": {
                    tag: {"total": s["total"], "hit1": s["hit1"], "hit3": s["hit3"], "hit5": s["hit5"]}
                    for tag, s in by_tag.items()
                },
                "items": detail,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    md_path = os.path.join(res_dir, f"retrieval_{date}_{seq}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 检索评估 · {date}\n\n")
        f.write(f"- top1 {pct(hits_1, total)}\n")
        f.write(f"- top3 {pct(hits_3, total)}\n")
        f.write(f"- top5 {pct(hits_5, total)}\n")
        f.write(f"- MRR {mrr:.3f} · 平均不同文档数 {avg_distinct:.2f} · 未命中 {len(misses)}\n\n")
        f.write("## 未命中清单\n\n")
        if misses:
            for m in misses:
                f.write(f"- [{m['tag']}] {m['question']}\n")
                f.write(f"  - 期望：{m['expect']}\n")
                f.write(f"  - 实际：{m['got']}\n")
        else:
            f.write("（无）\n")

    warnings = []
    if top5_rate < WARN_TOP5:
        warnings.append(f"top5 {top5_rate:.0%} 低于阈值 {WARN_TOP5:.0%}")
    if mrr < WARN_MRR:
        warnings.append(f"MRR {mrr:.3f} 低于阈值 {WARN_MRR}")
    if warnings:
        print("\n⚠️ 告警：" + "；".join(warnings))

    # ---- MLflow ----
    try:
        from scripts import eval_tracking

        eval_tracking.init_tracking()
        recall_k = max(TOPK * 4, 16)
        eval_tracking.log_run(
            run_name=f"retrieval-{dt.datetime.now().strftime('%H%M%S')}",
            params={
                "task": "retrieval",
                "embedding_model": config.EMBEDDING_MODEL,
                "rerank_model": config.RERANK_MODEL if config.RERANK_API_KEY else "off",
                "top_k": TOPK,
                "recall_k": recall_k,
                "git_commit": eval_tracking.git_commit(),
                "qa_hash": eval_tracking.file_sha256(EVAL_PATH),
                "corpus_hash": eval_tracking.file_sha256(
                    os.path.join(ROOT, "scripts", "corpus_manifest.py")
                ),
            },
            metrics={
                "top1": round(top1_rate, 4),
                "top3": round(top3_rate, 4),
                "top5": round(top5_rate, 4),
                "mrr": round(mrr, 4),
                "avg_distinct_docs": round(avg_distinct, 4),
                "miss_count": len(misses),
            },
            tags={"task": "retrieval", "date": date},
            artifact_path=json_path,
        )
        print("\nMLflow run 已记录（mlflow ui 可查看对比）")
    except Exception as e:
        print(f"\nMLflow 记录失败（不影响评测）：{e}")

    print(f"逐题结果：{json_path}")
    print(f"人读报告：{md_path}")


if __name__ == "__main__":
    main()