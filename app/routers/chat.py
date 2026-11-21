"""问答路由（docs/API.md 第 5 节契约）：POST /api/chat → text/event-stream。

生成器为普通 def（FastAPI 自动放入线程池执行，模型流式调用不阻塞事件循环）；
`event: done` 由本层在 answer_stream 正常结束后补发，携带新落库的
conversationId/messageId；answer_stream 已置 state["errored"] 时只发 error 不发 done。
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import config
from app.auth import get_current_user
from app.db import User
from app.schemas import ChatIn
from app.services import agent
from app.services import rag

router = APIRouter(prefix="/api/chat", tags=["chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # 关掉反代缓冲，保证逐 token 到达
    "Connection": "keep-alive",
}


@router.post("")
def chat(body: ChatIn, user: User = Depends(get_current_user)):
    def stream():
        state: dict = {}
        try:
            if config.AGENT_MODE:
                yield from agent.agent_answer_stream(user, body.question, body.conversation_id, state, body.document_ids)
            else:
                yield from rag.answer_stream(
                    user, body.question, body.document_ids, body.conversation_id, state
                )
        except Exception:  # 生成器内部未兜住的最后防线：以 error 帧收尾
            rag.log.exception("SSE 流异常 user=%s", user.id)
            yield rag.sse("error", {"message": "系统错误"})
            state["errored"] = True
        if not state.get("errored"):
            done_payload = {
                "conversationId": state.get("conversationId"),
                "messageId": state.get("messageId"),
            }
            # 过程指标随 done 一并返回（前端忽略未知字段，向后兼容）
            if state.get("metrics"):
                done_payload["metrics"] = state["metrics"]
            yield rag.sse("done", done_payload)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=_SSE_HEADERS)