"""Agent 工具注册中心（层1）：工具 schema + 统一执行 + 参数校验 + 异常兜底。

新增一个工具只需两步：
1. 在 TOOL_SCHEMAS 登记它的 function 定义（模型看到的）；
2. 在 _EXECUTORS 登记执行函数（签名 user, db, args -> dict）。

执行函数统一返回 {"data": ...} 或 {"error": "..."}。渲染成文本、引用编号由
rag.py 的 agent 循环负责——编号是跨多次 search_docs 的全局递增，属循环层而不是
单个工具层。
"""
import logging

from pydantic import BaseModel, Field

from app.repositories.summary import summarize
from app.services import index

log = logging.getLogger("app")


class SearchDocsArgs(BaseModel):
    """search_docs 入参：query 必填，top_k 夹在 [5, 10]，缺省 5。"""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=5, le=10)


# 喂给模型的 OpenAI function 定义（agent 循环直接透传）
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "在健身知识库（个人上传 + 公共语料）检索资料，返回带出处的文本块。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题或关键词"},
                    "top_k": {"type": "integer", "description": "返回块数（5~10，默认 5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_data",
            "description": "查询当前用户的真实记录：30 天容量、体重变化、近 7 天睡眠、酸痛度、目标进度、近 7 天饮食、忌口；没有任何记录时返回 has_data=false。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _search_docs(user, db, args: dict) -> dict:
    try:
        p = SearchDocsArgs.model_validate(args or {})
    except Exception as e:
        return {"error": f"参数错误：{e}"}
    hits = index.retrieve(user.id, p.query, top_k=p.top_k)
    return {"data": hits}


def _get_my_data(user, db, args: dict) -> dict:
    return {"data": summarize(db, user.id)}


_EXECUTORS = {
    "search_docs": _search_docs,
    "get_my_data": _get_my_data,
}


def execute(user, db, name: str, args: dict) -> dict:
    """统一执行入口：按名查表 → 校验并执行 → 异常兜底回填 error。"""
    if name not in _EXECUTORS:
        return {"error": f"未知工具：{name}"}
    try:
        return _EXECUTORS[name](user, db, args or {})
    except Exception as e:
        log.warning("工具 %s 执行失败: %s", name, e)
        return {"error": f"工具执行失败：{e}"}