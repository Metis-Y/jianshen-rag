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
import time
# Iterator：标注 SSE 生成器逐帧产出 str 的返回类型
from typing import Iterator

# OpenAI 官方 SDK 客户端；配合 base_url 可调用 OpenAI 兼容服务（本项目为硅基流动）
from openai import OpenAI

from app import config
from app.db import Conversation, Message, SessionLocal, User
from app.repositories.summary import fmt_num, summarize
from app.services import index

log = logging.getLogger("app")

# 信息门控兜底文案：既无检索资料、也无任何用户记录时直接返回，不调用模型
_NO_CONTENT = "知识库和记录里都没有相关内容"

# 系统提示词作为 messages 的 system 角色，规定引用编号、真实数据、拒答条件与忌口约束
_SYSTEM_PROMPT = (
    "你是健身私教助手，职责范围只有健身、训练、饮食、睡眠恢复。任何超出范围的问题（人物、时事、编程、通用知识），"
    "即使你知道答案也不回答、不展开、不编造。”"
    "回答时只能依据下面提供的【资料】与【我的数据】，并遵守规则：\n"
    "1. 知识类问题：只依据【资料】回答，禁止编造资料里没有的信息，引用处句末标注编号 [n]。\n"
    "2. 自身状态类问题（训练/体重/睡眠/恢复/饮食）：只依据【我的数据】的真实数字，禁止编造；\n"
    "   没有相关记录就明确回答“记录不足，无法判断”。\n"
    "3. 按来源取舍，不要误报“没有”：\n"
    "   - 有【资料】但无【我的数据】→ 依据资料回答，不要说“知识库中没有相关内容”；\n"
    "   - 有【我的数据】但无【资料】→ 用真实数字回答，并说明“知识库文档中没有对应内容”。\n"
    "4. 只有【资料】和【我的数据】都为空时，才回答“知识库和记录里都没有相关内容”。\n"
    "5. 用中文，简明条理，必须避开【我的数据】中标注的忌口。"
)


def sse(event: str, data: dict | list) -> str:
    """拼接 SSE 事件帧；json.dumps 会转义换行为 \\n，保证 data 单行合法。"""
    # SSE 帧 = event 行 + data 行 + 空行；ensure_ascii=False 让中文不被转成 \uXXXX 转义
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _materials_block(chunks: list[dict]) -> str:
    """【资料】块：按检索顺序编号 [1][2]…，含 doc_title/source/text。"""
    parts = ["【资料】"]
    # 编号从 1 开始，与系统提示词要求的 [1][2] 引用标注一一对应
    for i, c in enumerate(chunks, start=1):
        src = f"（{c['source']}）" if c.get("source") else ""
        parts.append(f"[{i}]《{c['doc_title']}》{src}\n{c['text']}")
    return "\n\n".join(parts)


def _my_data_block(snap: dict) -> str:
    """【我的数据】块：仅有数据的行才出现（容量/体重/恢复/目标进度/忌口）。"""
    lines: list[str] = []
    # 仅当有历史训练时才输出 30 天容量；完全没有训练记录时整行省略
    if snap["has_any_workout"]:
        lines.append(f"近30天训练总容量：{fmt_num(snap['volume30'])}kg")
    # 近 3 次训练已按时间升序拼成“日期：容量”，模型可直接比较趋势
    if snap.get("recent_sessions"):
        lines.append("近3次训练（日期：容量）：" + "、".join(snap["recent_sessions"]))
    # 力量目标进度：value 是目标重量、mx 是历史最好成绩，按两者是否存在分三种展示
    for g in snap.get("goal_progress", []):
        name, value, mx = g["name"], g["value"], g["max"]
        if value is None:
            if mx is not None:
                lines.append(f"{name}目前最好成绩：{fmt_num(mx)}kg")
        elif mx is not None:
            # 还差 = 目标重量 - 当前最好成绩；已达标时钳制为 0，避免出现负数
            left = max(0.0, value - mx)
            lines.append(
                f"{name}进度：目前 {fmt_num(mx)}kg / 目标 {fmt_num(value)}kg"
                f"（还差 {fmt_num(round(left, 1))}kg）"
            )
        else:
            lines.append(f"{name}目标：{fmt_num(value)}kg（暂无相关动作记录）")
    # 体重行：最新体重 + 近 30 天首尾差值（窗口内不足两条时差值为 None 或 0）
    if snap["latest_weight"] is not None:
        delta = snap["weight_delta"]
        delta_txt = ("+" if delta > 0 else "") + str(delta)
        lines.append(f"最新体重：{snap['latest_weight']}kg（近30天变化 {delta_txt}kg）")
    # 近 7 天平均睡眠；无睡眠记录时整行省略
    if snap.get("avg_sleep") is not None:
        lines.append(f"近7天平均睡眠：{snap['avg_sleep']}小时")
    if snap.get("latest_soreness") is not None:
        lines.append(f"最近记录酸痛度：{snap['latest_soreness']}/5")
    # 近 7 天饮食记录（日期：餐次：内容），供"最近吃了什么"类问题取真实内容
    if snap.get("recent_diets"):
        lines.append("近7天饮食：" + "、".join(snap["recent_diets"]))
    # 用户自填目标（增肌/减脂等），与结构化的力量/体重目标分开表达
    if snap["goal"]:
        lines.append(f"目标：{snap['goal']}")
    # 体重目标进度：用 abs 取绝对差，增重与减重都只报“相差多少”
    if snap.get("target_weight") is not None and snap["latest_weight"] is not None:
        diff = abs(round(snap["latest_weight"] - snap["target_weight"], 1))
        lines.append(
            f"体重进度：当前 {fmt_num(snap['latest_weight'])}kg / 目标 {fmt_num(snap['target_weight'])}kg"
            f"（相差 {fmt_num(diff)}kg）"
        )
    # 忌口列表：系统提示词要求模型给出饮食建议时必须避开
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
    # 复用前端传入的会话；会话不存在或不属于当前用户时降级为新建
    if conversation_id is not None:
        # db.get(Model, 主键)：按主键取一行，未命中返回 None
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id != user_id:
            log.warning("会话 %s 不属于用户 %s，另建新会话", conversation_id, user_id)
            conv = None
    # 新建会话：标题取提问前 30 字，正好充当会话列表的简短标题
    if conv is None:
        conv = Conversation(user_id=user_id, title=question[:30])
        # db.add：把对象放入 session 的待持久化集合（此时尚未执行 INSERT）
        db.add(conv)
        # flush 发出 INSERT 但暂不提交，同时把自增主键回填到 conv.id，供消息外键使用
        db.flush()  # 先拿到 conv.id

    # 用户提问与助手回答放在同一事务中成对写入，避免只落一半
    db.add(Message(conversation_id=conv.id, role="user", content=question))
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=citations or None,
    )
    db.add(assistant)
    # 再 flush 一次回填 assistant.id，作为 state 里的 messageId 回传给路由层
    db.flush()
    # 先取出 id 再 commit：commit 默认会 expire 对象属性，之后访问会触发额外查询
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
    # 每次调用先复位错误标记；路由层据此判断是否补发 done（error 为终态）
    state["errored"] = False
    # SessionLocal()：新建独立数据库会话；生成器跑在线程池线程，不能复用请求依赖的会话
    db = SessionLocal()
    try:
        # 1) 向量检索（本人文档或公共文档；document_ids 非空时限定范围）
        try:
            chunks = index.retrieve(user.id, question, document_ids=document_ids)
        except RuntimeError as exc:  # 配置类错误（如 API key 缺失）直接透出可读信息
            log.warning("检索配置异常 user=%s: %s", user.id, exc)
            # 检索配置类错误：标记错误、推 error 帧后返回；error 之后不会再补 done
            state["errored"] = True
            yield sse("error", {"message": str(exc)})
            return
        # 非配置类异常（网络/索引等）统一兜底，只回可读提示，不向前端暴露堆栈
        except Exception:
            log.exception("检索失败 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "检索服务异常，请稍后重试"})
            return

        # 2) 用户数据快照（每次提问都带，模型自行决定用不用；口径见 repositories/summary）
        # 聚合真实数据快照（容量/体重/睡眠/酸痛/目标/忌口），统计口径见 repositories/summary
        snap = summarize(db, user.id)

        # 信息门控：既无资料命中、也无任何记录时才不调模型；其余一律调模型，
        # 用资料还是用数据、"记录不足"/"没有相关内容"，全由模型按系统规则自行判断。
        if (
            not chunks
            and not snap["has_any_workout"]
            and not snap["has_any_metric"]
            and not snap["has_any_diet"]
        ):
            state["errored"] = True
            yield sse("error", {"message": _NO_CONTENT})
            return

        # 3) citations 事件（首个 token 前）
        # citations 只带编号/标题/来源/正文前 80 字，供前端展示引用卡片，不重复回传全文
        citations = [
            {
                "idx": i,
                "docTitle": c["doc_title"],
                "source": c["source"],
                "text": (c["text"] or "")[:80],
            }
            for i, c in enumerate(chunks, start=1)
        ]
        # citations 必须先于首个 message 发出，前端才能先建引用、再逐字填充回答
        yield sse("citations", citations)

        # 4) Prompt 双块组装
        # 双块组装：有资料命中才加【资料】块，有用户数据才加【我的数据】块，最后附问题
        blocks: list[str] = []
        if chunks:
            blocks.append(_materials_block(chunks))
        my_data = _my_data_block(snap)
        if my_data:  # 有数据 → 附结构化数字
            blocks.append(f"【我的数据】\n{my_data}")
        # 块间空行分隔、问题固定放最后，避免长资料把问题淹没
        prompt = "\n\n".join(blocks + [f"问题：{question}"])
        # 标准 Chat Completions 结构：system 定规则，user 携带资料/数据/问题
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # 5) 模型流式输出 → 逐 token 发 message 事件
        # 未配置对话 key 时无法建流，提前返回可读错误（此时尚未推送任何 message）
        if not config.CHAT_API_KEY:
            state["errored"] = True
            yield sse("error", {"message": "CHAT_API_KEY 未配置"})
            return
        try:
            # OpenAI 兼容客户端：base_url 指向硅基流动，复用 OpenAI SDK 的协议与参数
            client = OpenAI(
                api_key=config.CHAT_API_KEY,
                base_url=config.CHAT_BASE_URL,
                timeout=config.CHAT_TIMEOUT,
            )
            # 流式对话补全：stream=True 返回可迭代的 chunk 流，而非一次性完整响应
            stream = client.chat.completions.create(
                model=config.CHAT_MODEL,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                # 思考开关（MiMo v2.6 用 thinking.type）：配置了 CHAT_THINKING 才透传，留空=服务端默认
                extra_body={"thinking": {"type": config.CHAT_THINKING}} if config.CHAT_THINKING else None,
            )
        # 建连/鉴权/模型名错误在此兜底；此时还没推正文，可安全用 error 收尾
        except Exception:
            log.exception("chat 流建立失败 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "模型服务不可用"})
            return

        full = ""
        usage: dict | None = None
        t_start = time.perf_counter()
        first_token_ms: float | None = None
        try:
            # 逐 chunk 读取增量；choices 为空（心跳/空包或仅带 usage 的收尾包）时跳过正文
            for chunk in stream:
                if getattr(chunk, "usage", None):  # 收尾只带 usage 的包：先记下
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                if not chunk.choices:
                    continue
                # 取首个候选的增量文本；None 表示该 chunk 没有正文（如仅带角色信息）
                delta = chunk.choices[0].delta.content
                if delta:
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - t_start) * 1000)
                    full += delta
                    # 边收边推，同时累积 full；流结束后用 full 落库完整回答
                    yield sse("message", {"delta": delta})
        # 流中断：已推内容无法撤回，只补 error 帧，不回滚也不再补 done
        except Exception:
            log.exception("chat 流中断 user=%s", user.id)
            state["errored"] = True
            yield sse("error", {"message": "回答生成中断，请重试"})
            return

        # 过程指标：随 done 事件回传，供端到端评估采集 usage/延迟/引用数
        state["metrics"] = {
            "mode": "rag",
            "latency_ms": round((time.perf_counter() - t_start) * 1000),
            "first_token_ms": first_token_ms,
            "usage": usage,
            "citations": len(citations),
        }

        # 6) 流结束：落库（与上文聚合同一 session），失败仅记日志不影响已推流
        try:
            # 落库失败不影响已推流内容：前端已展示回答，仅会话历史缺这条，记日志即可
            conv_id, msg_id = _persist(db, user.id, question, full, citations, conversation_id)
            # 成功落库后把 id 写入 state，路由层在生成器结束后据此补发 done 事件
            state["conversationId"] = conv_id
            state["messageId"] = msg_id
        except Exception:
            log.exception("问答落库失败 user=%s", user.id)
            # 落库失败也显式置 None，表示本次没有可回传的会话/消息 id
            state["conversationId"] = None
            state["messageId"] = None
    # 正常结束、提前 return、异常退出都会走到这里，确保会话关闭不泄漏连接
    finally:
        db.close()


