"""会话/反馈路由（docs/API.md 第 6 节契约）。

- /api/conversations：列表 / 消息 / 删除（全部归属校验）
- /api/messages/{id}/feedback：回答反馈（同一用户同消息幂等覆盖）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import Conversation, Feedback, Message, User, get_db
from app.schemas import FeedbackIn

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
feedback_router = APIRouter(prefix="/api/messages", tags=["feedback"])


def _get_owned_conv(db: Session, user: User, conv_id: int) -> Conversation:
    """会话归属校验：不存在 404，非本人 403。"""
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conv.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return conv


def _message_out(m: Message, feedback: bool | None = None) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": m.citations or [],
        "feedback": feedback,
        "createdAt": m.created_at.isoformat(),
    }


@router.get("")
def list_conversations(
    page: int = 1,
    size: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = (
        db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id))
        or 0
    )
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return resp.ok(
        {
            "total": total,
            "page": page,
            "size": size,
            "list": [
                {"id": c.id, "title": c.title, "createdAt": c.created_at.isoformat()}
                for c in rows
            ],
        }
    )


@router.get("/{conv_id}/messages")
def list_messages(
    conv_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conv(db, user, conv_id)
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.asc())
    ).all()
    # 当前用户对各消息的反馈（true/false，未反馈为 null），供前端回显
    fb_map: dict[int, bool] = {}
    if rows:
        fbs = db.scalars(
            select(Feedback).where(
                Feedback.message_id.in_([m.id for m in rows]),
                Feedback.user_id == user.id,
            )
        ).all()
        fb_map = {fb.message_id: fb.is_positive for fb in fbs}
    return resp.ok({"list": [_message_out(m, fb_map.get(m.id)) for m in rows]})


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conv(db, user, conv_id)
    msg_ids = db.scalars(select(Message.id).where(Message.conversation_id == conv.id)).all()
    if msg_ids:
        db.execute(delete(Feedback).where(Feedback.message_id.in_(msg_ids)))
        db.execute(delete(Message).where(Message.conversation_id == conv.id))
    db.delete(conv)
    db.commit()
    return resp.ok()


@feedback_router.post("/{message_id}/feedback")
def feedback(
    message_id: int,
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = db.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    conv = db.get(Conversation, msg.conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该消息")

    fb = db.scalar(
        select(Feedback).where(
            Feedback.message_id == message_id,
            Feedback.user_id == user.id,
        )
    )
    if fb is None:
        fb = Feedback(message_id=message_id, user_id=user.id, is_positive=body.positive)
        db.add(fb)
    else:
        fb.is_positive = body.positive
    db.commit()
    return resp.ok()