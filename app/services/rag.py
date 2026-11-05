"""RAG 问答链路（D4）：检索 → 用户真实数据聚合 → 双块 Prompt → SSE 流式回答 → 落库。

- SSE 帧统一由 sse() 拼接（JSON data 单行，不含裸换行）；
- `event: done` 由路由层在生成器正常结束后补发，本模块通过 state 字典
  回传落库后的 conversationId/messageId；中途 error 为终态（不再发 done）；
- 生成器内检索/聚合/落库共用同一个 SessionLocal 会话（开在生成器线程里，
  与请求依赖线程解耦），异常兜底记录日志、不影响已推流内容；
- 数据聚合口径在 app/repositories/summary（只给真实小数字，杜绝编造）。
"""
import json
import logging
from typing import Iterator

from openai import OpenAI

from app import config
from app.db import Conversation, Message, SessionLocal, User
from app.repositories.summary import fmt_num, summarize
from app.services import index

log = logging.getLogger("app")

_NO_CONTENT = "知识库和记录里都没有相关内容"

_SYSTEM_PROMPT = (
    "你是健身私教助手，请严格遵守以下回答规则：\n"
    "1. 资料类问题：只能依据【资料】中的内容回答，不得编造资料中没有的信息，"
    "并在相关句子末尾标注资料编号（如 [1]）。\n"
    "2. 关于用户自身状态/进展/训练/体重/恢复的问题：必须使用【我的数据】中的真实数字回答，"
    "不得编造；【我的数据】中没有相关记录时，直接回答“记录不足，无法判断”。\n"
    "3. 仅当【资料】和【我的数据】都不足以回答问题时，才直接回答“知识库中没有相关内容”；"
    "已经用【我的数据】回答过，不要再附加这句话。\n"
    "4. 回答使用中文，简明、条理清晰；必须避开【我的数据】中标注的忌口。"
)


def sse(event: str, data: dict | list) -> str:
    """拼接 SSE 事件帧；json.dumps 会转义换行为 \\n，保证 data 单行合法。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _materials_block(chunks: list[dict]) -> str:
    """【资料】块：按检索顺序编号 [1][2]…，含 doc_title/source/text。"""
    parts = ["【资料】"]
    for i, c in enumerate(chunks, start=1):
        src = f"（{c['source']}）" if c.get("source") else ""
        parts.append(f"[{i}]《{c['doc_title']}》{src}\n{c['text']}")
    return "\n\n".join(parts)


def _my_data_block(snap: dict) -> str:
    """【我的数据】块：仅有数据的行才出现（容量/体重/恢复/目标进度/忌口）。"""
    lines: list[str] = []
    if snap["has_any_workout"]:
        lines.append(f"近30天训练总容量：{fmt_num(snap['volume30'])}kg")
    if snap.get("recent_sessions"):
        lines.append("近3次训练（日期：容量）：" + "、".join(snap["recent_sessions"]))
    for g in snap.get("goal_progress", []):
        name, value, mx = g["name"], g["value"], g["max"]
        if value is None:
            if mx is not None:
                lines.append(f"{name}目前最好成绩：{fmt_num(mx)}kg")
        elif mx is not None:
            left = max(0.0, value - mx)
            lines.append(
                f"{name}进度：目前 {fmt_num(mx)}kg / 目标 {fmt_num(value)}kg"
                f"（还差 {fmt_num(round(left, 1))}kg）"
            )
        else:
            lines.append(f"{name}目标：{fmt_num(value)}kg（暂无相关动作记录）")
    if snap["latest_weight"] is not None:
        delta = snap["weight_delta"]
        delta_txt = ("+" if delta > 0 else "") + str(delta)
        lines.append(f"最新体重：{snap['latest_weight']}kg（近30天变化 {delta_txt}kg）")
    if snap.get("avg_sleep") is not None:
        lines.append(f"近7天平均睡眠：{snap['avg_sleep']}小时")
    if snap.get("latest_soreness") is not None:
        lines.append(f"最近记录酸痛度：{snap['latest_soreness']}/5")
    if snap["goal"]:
        lines.append(f"目标：{snap['goal']}")
    if snap.get("target_weight") is not None and snap["latest_weight"] is not None:
        diff = abs(round(snap["latest_weight"] - snap["target_weight"], 1))
        lines.append(
            f"体重进度：当前 {fmt_num(snap['latest_weight'])}kg / 目标 {fmt_num(snap['target_weight'])}kg"
            f"（相差 {fmt_num(diff)}kg）"
        )
    if snap["allergies"]:
        lines.append(f"忌口：{'、'.join(snap['allergies'])}")
    return "\n".join(lines)


def _persist(
    db,
    user_id: int,
    question: str,
    answer: str,
    citations: list[dict],
    conversation_id: int | None,
) -> tuple[int, int]:
    """同一 db session 落库：user 消息 + assistant 消息（含 citations/完整 content），
    会话不存在则创建（title 取提问前 30 字）；会话不属于当前用户时另建新会话。"""
    conv: Conversation | None = None
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id != user_id:
            log.warning("会话 %s 不属于用户 %s，另建新会话", conversation_id, user_id)
            conv = None
    if conv is None:
        conv = Conversation(user_id=user_id, title=question[:30])
        db.add(conv)
        db.flush()  # 先拿到 conv.id

    db.add(Message(conversation_id=conv.id, role="user", content=question))
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=citations or None,
    )
    db.add(assistant)
    db.flush()
    conv_id, msg_id = conv.id, assistant.id
    db.commit()
    return conv_id, msg_id


def answer_stream(
    user: User,
    question: str,
    document_ids: list[int] | None = None,
    conversation_id: int | None = None,
    state: dict | None = None,
) -> Iterator[str]:
    """问答 SSE 生成器（普通 def，随路由放入线程池执行）。

    事件序列：citations → message…；异常/无内容 → error（终态）。
    成功后向 state 写入 {"conversationId", "messageId"}，路由层据此补发 done；
    任一 error/异常分支会把 state["errored"]=True。
    """
    state = state if state is not None else {}
    state["errored"] = False
    db = SessionLocal()
    try:
        # 1) 向量检索（本人文档或公共文档；document_ids 非空时限定范围）
        try:
            chunks = index.retrieve(user.id, question, document_ids=document_ids)
        except RuntimeError as exc:  # 配置类错误（如 API key 缺失）直接透出可读信息
            log.warning("检索配置异常 user=%s: %s", user.id, exc)
            state["errored"] = True
            yield sse("error", {"message": str(exc)})
            return
        except Exception:
            log.exception("检索失败 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "检索服务异常，请稍后重试"})
            return

        # 2) 用户数据快照（每次提问都带，模型自行决定用不用；口径见 repositories/summary）
        snap = summarize(db, user.id)

        # 信息门控：既无资料命中、也无任何记录时才不调模型；其余一律调模型，
        # 用资料还是用数据、"记录不足"/"没有相关内容"，全由模型按系统规则自行判断。
        if not chunks and not snap["has_any_workout"] and not snap["has_any_metric"]:
            state["errored"] = True
            yield sse("error", {"message": _NO_CONTENT})
            return

        # 3) citations 事件（首个 token 前）
        citations = [
            {
                "idx": i,
                "docTitle": c["doc_title"],
                "source": c["source"],
                "text": (c["text"] or "")[:80],
            }
            for i, c in enumerate(chunks, start=1)
        ]
        yield sse("citations", citations)

        # 4) Prompt 双块组装
        blocks: list[str] = []
        if chunks:
            blocks.append(_materials_block(chunks))
        my_data = _my_data_block(snap)
        if my_data:  # 有数据 → 附结构化数字
            blocks.append(f"【我的数据】\n{my_data}")
        prompt = "\n\n".join(blocks + [f"问题：{question}"])
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # 5) 模型流式输出 → 逐 token 发 message 事件
        if not config.CHAT_API_KEY:
            state["errored"] = True
            yield sse("error", {"message": "CHAT_API_KEY 未配置"})
            return
        try:
            client = OpenAI(api_key=config.CHAT_API_KEY, base_url=config.CHAT_BASE_URL)
            stream = client.chat.completions.create(
                model=config.CHAT_MODEL,
                messages=messages,
                stream=True,
            )
        except Exception:
            log.exception("chat 流建立失败 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "模型服务不可用"})
            return

        full = ""
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    full += delta
                    yield sse("message", {"delta": delta})
        except Exception:
            log.exception("chat 流中断 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "回答生成中断，请重试"})
            return

        # 6) 流结束：落库（与上文聚合同一 session），失败仅记日志不影响已推流
        try:
            conv_id, msg_id = _persist(db, user.id, question, full, citations, conversation_id)
            state["conversationId"] = conv_id
            state["messageId"] = msg_id
        except Exception:
            log.exception("问答落库失败 user=%s", user.id)
            state["conversationId"] = None
            state["messageId"] = None
    finally:
        db.close()