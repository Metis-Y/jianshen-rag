"""M5 端到端评估：真实问答 + LLM-as-judge 要点覆盖率（09 方案实现）。

用法（项目根目录，需服务已在线）：
    ./.venv/Scripts/python.exe scripts/run_e2e_eval.py [--limit N] [--judge-model ...]

- 前置：http://127.0.0.1:8000/docs 健康、demo 账号存在（否则先跑 seed_demo.py）
- 走真实 POST /api/chat（demo token），流式读完整回答 + citations
- 判卷：judge 模型判断回答覆盖了题库 keyPoints 的哪几条（意思相同即算覆盖，不抠字眼）
- judge 关闭思考模式（thinking.type=disabled），避免思考串扰 JSON 解析；答案生成不受影响
- 输出：平均要点覆盖率（主指标）、按 tag 分组、未完成题清单；
  跑前记录 demo 最大会话 id，跑完删除新增会话（不污染演示数据）
- 逐题结果落盘 results/e2e_<日期>_<judge模型>.json，供换模型后 diff
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI  # noqa: E402

from app import config  # noqa: E402
from app.services.rag import _SYSTEM_PROMPT  # noqa: E402
from scripts.eval_common import load_eval_set  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(ROOT, "tests", "eval_set.md")
BASE = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8000")
DEMO_USER = os.getenv("EVAL_DEMO_USER", "demo")
DEMO_PASS = os.getenv("EVAL_DEMO_PASS", "demo1234")
STREAM_TIMEOUT = 300

_JUDGE_SYSTEM = (
    "你是评估裁判。判断助手回答是否覆盖了每一条要点，意思相同即算覆盖，不抠字眼。"
    '只输出 JSON：{"covered":[true,false,...],"notes":"一句话"}，不要输出任何其他内容。'
)


def _request(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def _login() -> str:
    data = _request("POST", "/api/auth/login", body={"username": DEMO_USER, "password": DEMO_PASS})
    token = (data.get("data") or {}).get("token")
    if not token:
        sys.exit(f"demo 账号登录失败：{data}")
    return token


def _stream_chat(token: str, question: str) -> tuple:
    """返回 (answer, citations, status)；status = ok / generation_failed。"""
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"question": question}).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    answer = ""
    citations: list = []
    errored: str | None = None
    try:
        with urllib.request.urlopen(req, timeout=STREAM_TIMEOUT) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    continue
                data = json.loads(payload)
                if isinstance(data, list):       # citations 帧
                    citations = data
                elif "delta" in data:            # message 帧
                    answer += data["delta"]
                elif "messageId" in data:        # done 帧
                    pass
                else:                            # error 帧 {"message": ...}
                    errored = data.get("message")
    except Exception as e:  # 网络/上游异常一律记为生成失败
        errored = str(e)
    if errored or not answer.strip():
        return None, citations, "generation_failed"
    return answer, citations, "ok"


def _judge(client: OpenAI, model: str, question: str, keypoints: list, answer: str):
    """判卷：返回 (covered 列表, notes)；失败返回 (None, 'judge_failed')。"""
    user = (
        f"问题：{question}\n"
        f"答案要点：{json.dumps(keypoints, ensure_ascii=False)}\n"
        f"助手回答：\n{answer}"
    )
    for attempt in range(2):
        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {"role": "user", "content": user},
                ],
            }
            # 第一次强关思考；若模型不认该参数而报错，第二次退回不带 extra_body
            if attempt == 0:
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            data = json.loads(content)
            covered = data.get("covered")
            notes = str(data.get("notes", ""))
            if isinstance(covered, list) and len(covered) == len(keypoints):
                return covered, notes
        except Exception:
            continue
    return None, "judge_failed"


def _conversation_ids(token: str) -> list:
    ids: list = []
    page = 1
    while True:
        data = _request("GET", f"/api/conversations?page={page}&size=100", token=token)
        lst = (data.get("data") or {}).get("list") or []
        if not lst:
            break
        ids += [c["id"] for c in lst]
        if len(lst) < 100:
            break
        page += 1
    return ids


def _cleanup(token: str, keep_max_id: int) -> int:
    deleted = 0
    for cid in _conversation_ids(token):
        if cid > keep_max_id:
            _request("DELETE", f"/api/conversations/{cid}", token=token)
            deleted += 1
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全部）")
    parser.add_argument("--judge-model", default=None, help="判卷模型（默认=CHAT_MODEL）")
    args = parser.parse_args()

    try:
        urllib.request.urlopen(BASE + "/docs", timeout=10)
    except Exception:
        sys.exit(f"服务未在线（{BASE}/docs 打不开），请先启动 uvicorn")

    items = load_eval_set(EVAL_PATH)
    if args.limit:
        items = items[: args.limit]

    token = _login()
    judge_model = args.judge_model or config.CHAT_MODEL
    judge_client = OpenAI(api_key=config.CHAT_API_KEY, base_url=config.CHAT_BASE_URL)

    max_id = max(_conversation_ids(token), default=0)
    print(f"CHAT_MODEL={config.CHAT_MODEL}  JUDGE_MODEL={judge_model}  题数={len(items)}")

    total_covered = 0
    total_kp = 0
    by_tag: dict = {}
    failed: list = []
    detail: list = []

    for item in items:
        q = item["question"]
        tag = item.get("tag", "未分类")
        kps = item.get("keyPoints") or []
        stat = by_tag.setdefault(tag, {"covered": 0, "kp": 0, "answered": 0})

        answer, citations, status = _stream_chat(token, q)
        rec = {"question": q, "tag": tag, "keyPoints": kps, "status": status, "answer": answer}
        if status != "ok":
            failed.append({"question": q, "tag": tag, "reason": status})
            detail.append(rec)
            continue

        covered, notes = _judge(judge_client, judge_model, q, kps, answer)
        rec["notes"] = notes
        if covered is None:
            failed.append({"question": q, "tag": tag, "reason": "judge_failed"})
            detail.append(rec)
            continue

        covered_count = sum(1 for c in covered if c)
        stat["answered"] += 1
        stat["covered"] += covered_count
        stat["kp"] += len(kps)
        total_covered += covered_count
        total_kp += len(kps)
        rec["covered"] = covered
        rec["coverage"] = round(covered_count / len(kps), 2) if kps else None
        detail.append(rec)

    cleaned = _cleanup(token, max_id)

    if total_kp:
        print(f"\n平均要点覆盖率：{total_covered}/{total_kp} = {total_covered / total_kp:.0%}")
    else:
        print("\n平均要点覆盖率：无有效题（全部生成失败/判卷失败）")
    print("\n按题型：")
    for tag, stat in by_tag.items():
        cov = f"{stat['covered']}/{stat['kp']}" if stat["kp"] else "0/0"
        print(f"  [{tag}] 覆盖 {cov}（有效 {stat['answered']} 题）")
    print(f"\n未完成 {len(failed)} 题：")
    for f_ in failed:
        print(f"  [{f_['tag']}] {f_['reason']}: {f_['question']}")
    print(f"\n已清理新增 demo 会话 {cleaned} 个")

    res_dir = os.path.join(ROOT, "results")
    os.makedirs(res_dir, exist_ok=True)
    safe_model = judge_model.replace("/", "_").replace(":", "_")
    res_path = os.path.join(res_dir, f"e2e_{dt.date.today().isoformat()}_{safe_model}.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": dt.date.today().isoformat(),
                "chat_model": config.CHAT_MODEL,
                "judge_model": judge_model,
                "avg_coverage": (total_covered / total_kp if total_kp else None),
                "items": detail,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"逐题结果已写入 {res_path}")

    # 人看的 MD 记录：背景 + 每题题目/回答/判卷评价，追加到 results/评测记录.md
    md_path = os.path.join(res_dir, "评测记录.md")
    md = []
    md.append(f"\n---\n\n## 记录 · {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"- 答题模型：{config.CHAT_MODEL}")
    md.append(f"- 判卷模型：{judge_model}")
    md.append(f"- 模式：{'工具调用 agent' if config.AGENT_MODE else '固定管道'}（AGENT_MODE={'on' if config.AGENT_MODE else 'off'}）")
    md.append(f"- 思考：{config.CHAT_THINKING or '服务端默认'}")
    md.append(f"- 题数：{len(items)}")
    if total_kp:
        md.append(f"- 平均要点覆盖率：{total_covered}/{total_kp} = {total_covered / total_kp:.0%}")
    md.append("\n### 系统提示词")
    md.append("```")
    md.append(_SYSTEM_PROMPT)
    md.append("```")
    md.append("\n### 按题型")
    for tag, stat in by_tag.items():
        cov = f"{stat['covered']}/{stat['kp']}" if stat["kp"] else "0/0"
        md.append(f"- {tag}：{cov}（有效 {stat['answered']} 题）")
    md.append("\n### 逐题")
    for rec in detail:
        md.append(f"\n#### {rec['question']}")
        md.append(f"- 题型：{rec['tag']}")
        if "covered" not in rec:
            if rec.get("status") == "generation_failed":
                md.append("- 状态：生成失败（超时或上游错误），未计入分母")
            else:
                md.append("- 状态：判卷失败，未计入分母")
            continue
        kps = rec.get("keyPoints") or []
        covered = rec.get("covered") or []
        missed = [kps[i] for i, c in enumerate(covered) if not c]
        md.append(f"- 要点：{'；'.join(kps)}")
        md.append(f"- 覆盖：{'、'.join('√' if c else '×' for c in covered)}")
        if missed:
            md.append(f"- 未覆盖：{'；'.join(missed)}")
        if rec.get("notes"):
            md.append(f"- 判官说明：{rec['notes']}")
        if rec.get("answer"):
            md.append("- 回答：")
            md.append("```")
            md.append(rec["answer"])
            md.append("```")
    with open(md_path, "a", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"评测记录已追加到 {md_path}")


if __name__ == "__main__":
    main()