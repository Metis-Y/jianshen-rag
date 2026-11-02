"""统一响应包络：code=1 成功（项目约定）。"""
from typing import Any


def ok(data: Any = None) -> dict:
    return {"code": 1, "message": "ok", "data": data}


def fail(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}