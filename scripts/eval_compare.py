"""阶段二：历史检索实验对比 + 回归告警。

读 MLflow `fitpal-eval` 里的 retrieval run，挑两条做对比：
- 默认：最新两次；`--a` / `--b` 可指定 run 名或 run_id（前缀即可）
- 输出：整体指标 A→B 涨跌、逐题变化（提升/变差/翻身/翻车）、回归告警；
  结果同时落到 results/compare_<时间>.md
- 逐题对比基于各 run 的逐题 JSON artifact（即 eval_retrieval 落的那份）

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/eval_compare.py
    ./.venv/Scripts/python.exe scripts/eval_compare.py --a retrieval-1405 --b retrieval-1530
"""
import argparse
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mlflow.tracking import MlflowClient  # noqa: E402

from scripts import eval_tracking  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARN_TOP5 = 0.9
WARN_MRR = 0.85


def _retrieval_runs(client: MlflowClient) -> list:
    exp = client.get_experiment_by_name(eval_tracking.EXPERIMENT)
    if exp is None:
        return []
    runs = client.search_runs(exp.experiment_id, order_by=["start_time DESC"])
    return [r for r in runs if (r.data.tags or {}).get("task") == "retrieval"]


def _find_run(client: MlflowClient, runs: list, ident: str):
    for r in runs:
        if r.info.run_name == ident or r.info.run_id == ident or r.info.run_id.startswith(ident):
            return r
    return None


def _items(client: MlflowClient, run) -> list:
    """下载该 run 的逐题 JSON artifact，返回 items 列表（没有则返回空）。"""
    arts = client.list_artifacts(run.info.run_id)
    art = next((a for a in arts if a.path.endswith(".json")), None)
    if art is None:
        return []
    tmp = tempfile.mkdtemp()
    local = client.download_artifacts(run.info.run_id, art.path, dst_path=tmp)
    with open(local, encoding="utf-8") as f:
        return json.load(f).get("items", [])


def _fmt_run(run) -> str:
    name = run.info.run_name or run.info.run_id[:8]
    t = dt.datetime.fromtimestamp(run.info.start_time / 1000).strftime("%m-%d %H:%M:%S")
    return f"{name}（{t}）"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=None, help="基线 run（名字或 id，可传前缀）")
    ap.add_argument("--b", default=None, help="目标 run（名字或 id，可传前缀）")
    args = ap.parse_args()

    eval_tracking.init_tracking()
    client = MlflowClient()
    runs = _retrieval_runs(client)

    if not runs:
        print("还没有 retrieval run，先跑 scripts/eval_retrieval.py")
        return

    if not args.a and not args.b and len(runs) < 2:
        r = runs[0]
        print(f"只有 {len(runs)} 条 retrieval run，暂无历史可对比；先跑一次新的 eval_retrieval.py")
        print(f"\n当前唯一 run：{_fmt_run(r)}")
        print("  metrics:", {k: round(v, 4) for k, v in r.data.metrics.items()})
        return

    b = _find_run(client, runs, args.b) if args.b else runs[0]
    a = _find_run(client, runs, args.a) if args.a else (runs[1] if not args.b else None)
    if a is None or b is None:
        print("找不到指定的 run，当前可选：")
        for r in runs:
            print(f"  - {r.info.run_name}  ({r.info.run_id[:8]})")
        return

    ma, mb = a.data.metrics, b.data.metrics
    items_a, items_b = _items(client, a), _items(client, b)

    buf: list[str] = []
    buf.append(f"基线 A：{_fmt_run(a)}")
    buf.append(f"目标 B：{_fmt_run(b)}")
    buf.append("")

    buf.append("== 整体指标 A → B ==")
    for k in ("top1", "top3", "top5", "mrr", "avg_distinct_docs", "miss_count"):
        va, vb = ma.get(k), mb.get(k)
        if va is None and vb is None:
            continue
        delta = "" if va is None or vb is None else f"  Δ {vb - va:+.4f}"
        buf.append(f"  {k:<18} {va} → {vb}{delta}")

    by_a = {it["question"]: it for it in items_a}
    changed = {"提升": [], "变差": [], "翻身": [], "翻车": []}
    for q, itb in {it["question"]: it for it in items_b}.items():
        ita = by_a.get(q)
        if ita is None:
            continue
        ra, rb = ita.get("best_rank"), itb.get("best_rank")
        ha, hb = ita.get("hit5", False), itb.get("hit5", False)
        if not ha and hb:
            changed["翻身"].append(q)
        elif ha and not hb:
            changed["翻车"].append(q)
        elif ha and hb and ra is not None and rb is not None:
            if rb < ra:
                changed["提升"].append(f"{q}（第{ra}名 → 第{rb}名）")
            elif rb > ra:
                changed["变差"].append(f"{q}（第{ra}名 → 第{rb}名）")

    n = sum(len(v) for v in changed.values())
    buf.append("")
    buf.append(f"== 逐题变化（{n} 题变动："
               f"提升 {len(changed['提升'])} · 变差 {len(changed['变差'])} · "
               f"翻身 {len(changed['翻身'])} · 翻车 {len(changed['翻车'])}）==")
    for label in ("翻车", "变差", "翻身", "提升"):
        for s in changed[label]:
            buf.append(f"  [{label}] {s}")

    warns = []
    if mb.get("top5", 1.0) < WARN_TOP5:
        warns.append(f"top5 {mb['top5']:.0%} 低于阈值 {WARN_TOP5:.0%}")
    if mb.get("mrr", 1.0) < WARN_MRR:
        warns.append(f"MRR {mb['mrr']:.3f} 低于阈值 {WARN_MRR}")
    buf.append("")
    buf.append("⚠️ 回归告警：" + "；".join(warns) if warns else "✅ 无回归告警（关键指标在阈值之上）")

    for line in buf:
        print(line)

    res_dir = os.path.join(ROOT, "results")
    os.makedirs(res_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H%M%S")
    report = os.path.join(res_dir, f"compare_{stamp}.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("# 检索实验对比\n\n```\n" + "\n".join(buf) + "\n```\n")
    print(f"\n对比报告：{report}")


if __name__ == "__main__":
    main()