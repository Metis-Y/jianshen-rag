"""Agent 问答（层1）：模型自选工具、多轮调用后回答（流式写法）。

与固定管道（app/services/rag.py 的 answer_stream）分离。每一轮都走流式：边收边攒
正文与工具调用片段，按"这轮有没有 tool_calls"判断该继续调工具还是给出最终答案——
因此最终答案只生成一次，不会先非流式生成再丢弃重生成。

共享的 SSE 帧、系统提示词、数据块渲染、落库从 rag.py 复用；异常降级回固定管道。
"""
import json
import logging
from typing import Iterator

from openai import OpenAI

from app import config
from app.db import SessionLocal, User
from app.services import tools
from app.services.rag import _SYSTEM_PROMPT, _my_data_block, _persist, answer_stream, sse

log = logging.getLogger("app")

# 追加到系统提示词之后的工具使用说明（轮数上限与 _MAX_ROUNDS 保持一致）
_AGENT_TOOL_HINT = (
    "你可以调用工具：资料类问题先用 search_docs 检索并引用返回里的 [n] 编号；"
    "关于用户自身状态的问题先用 get_my_data 查真实记录。必要时再追问，最多五轮。"
)

# 工具循环轮数上限：超过后强制生成最终回答
_MAX_ROUNDS = 5


def _stream_turn(client: OpenAI, messages: list[dict]) -> tuple[str, list[dict], str | None]:
    """流式跑一轮：攒正文 + 拼工具调用片段；返回 (正文, 工具调用列表, finish_reason)。"""
    stream = client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=messages,
        tools=tools.TOOL_SCHEMAS,
        stream=True,
        max_tokens=config.AGENT_MAX_OUTPUT_TOKENS,
        extra_body={"thinking": {"type": config.CHAT_THINKING}} if config.CHAT_THINKING else None,
    )
    text = ""
    finish: str | None = None
    calls: dict[int, dict] = {}
    for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason:
            finish = choice.finish_reason
        delta = choice.delta
        if delta.content:
            text += delta.content
        for tc in delta.tool_calls or []:
            slot = calls.setdefault(tc.index or 0, {"id": "", "name": "", "args": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function and tc.function.name:
                slot["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                slot["args"] += tc.function.arguments
    return text, [calls[i] for i in sorted(calls)], finish


def _build_citations(collected: list[dict]) -> list[dict]:
    """把收集到的检索命中块按全局顺序编号，生成 citations 事件数据。

正文里模型标注的 [n] 就是这里的 idx；生成最终回答前调用它拿到编号。
    """
    return [
        {
            "idx": i,
            "docTitle": h["doc_title"],
            "source": h.get("source") or "",
            "text": (h.get("text") or "")[:80],
        }
        for i, h in enumerate(collected, start=1)
    ]


def _render_search_hits(new_hits: list[dict], collected: list[dict], seen: set) -> str:
    """把新命中块去重、全局编号后渲染成文本（编号必须在最终生成前让模型看到才能标 [n]）。"""
    parts: list[str] = []
    for h in new_hits:
        key = (h.get("doc_id"), h.get("seq"))
        if key in seen:
            continue
        seen.add(key)
        collected.append(h)
        j = len(collected)
        src = f"（{h['source']}）" if h.get("source") else ""
        parts.append(f"[{j}]《{h['doc_title']}》{src}\n{h['text']}")
    return "\n\n".join(parts) if parts else "未检索到相关内容"


def agent_answer_stream(
    user: User,
    question: str,
    conversation_id: int | None = None,
    state: dict | None = None,
    document_ids: list[int] | None = None,
) -> Iterator[str]:
    state = state if state is not None else {}
    state["errored"] = False
    db = SessionLocal()
    try:
        if not config.CHAT_API_KEY:
            state["errored"] = True
            yield sse("error", {"message": "CHAT_API_KEY 未配置"})
            return

        client = OpenAI(
            api_key=config.CHAT_API_KEY,
            base_url=config.CHAT_BASE_URL,
            timeout=config.CHAT_TIMEOUT,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT + _AGENT_TOOL_HINT},
            {"role": "user", "content": question},
        ]

        collected: list[dict] = []
        seen: set = set()
        final_text = ""
        try:
            for _ in range(_MAX_ROUNDS):
                turn_text, tool_calls, finish = _stream_turn(client, messages)
                if not tool_calls:
                    # 本轮就是最终答案，无需再生成
                    final_text = turn_text
                    break
                if finish == "length":
                    # 被 max_tokens 截断：半截工具调用不可靠，放弃本轮，转兜底最终生成
                    final_text = ""
                    break

                # 先把 assistant 的工具调用消息回填，再逐条回填工具结果
                for i, c in enumerate(tool_calls):
                    c["_cid"] = c["id"] or f"call_{i}"
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn_text or None,
                        "tool_calls": [
                            {
                                "id": c["_cid"],
                                "type": "function",
                                "function": {"name": c["name"], "arguments": c["args"]},
                            }
                            for c in tool_calls
                        ],
                    }
                )
                for c in tool_calls:
                    name = c["name"]
                    args = json.loads(c["args"] or "{}")
                    result = tools.execute(user, db, name, args, document_ids)
                    if result.get("error"):
                        content = f"工具执行失败，请基于已有信息回答：{result['error']}"
                    else:
                        data = result.get("data")
                        if name == "search_docs":
                            content = _render_search_hits(data or [], collected, seen)
                        elif name == "get_my_data":
                            snap = data or {}
                            if snap.get("has_any_workout") or snap.get("has_any_metric") or snap.get("has_any_diet"):
                                content = _my_data_block(snap)
                            else:
                                content = "没有任何记录"
                        else:
                            content = "未知工具"
                    messages.append({"role": "tool", "tool_call_id": c["_cid"], "content": content})
        except Exception:
            log.warning("agent 循环失败，降级固定管道 user=%s", user.id)
            yield from answer_stream(user, question, document_ids, conversation_id, state)
            return

        citations = _build_citations(collected)
        yield sse("citations", citations)

        # 五轮都在调工具、始终没给正文时，强制生成一次兜底
        if not final_text:
            try:
                resp = client.chat.completions.create(
                    model=config.CHAT_MODEL,
                    messages=messages,
                    tools=tools.TOOL_SCHEMAS,
                    tool_choice="none",
                    stream=False,
                    max_tokens=config.AGENT_MAX_OUTPUT_TOKENS,
                    extra_body={"thinking": {"type": config.CHAT_THINKING}} if config.CHAT_THINKING else None,
                )
                final_text = resp.choices[0].message.content or ""
            except Exception:
                log.exception("agent 强制生成失败 user=%s", user.id)
                state["errored"] = True
                yield sse("error", {"message": "回答生成失败，请重试"})
                return

        yield sse("message", {"delta": final_text})

        try:
            conv_id, msg_id = _persist(db, user.id, question, final_text, citations, conversation_id)
            state["conversationId"] = conv_id
            state["messageId"] = msg_id
        except Exception:
            log.exception("问答落库失败 user=%s", user.id)
            state["conversationId"] = None
            state["messageId"] = None
    finally:
        db.close()