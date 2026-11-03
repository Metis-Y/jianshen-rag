"""应用入口：路由、生命周期、全局异常转包络。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import resp
from app.db import Base, engine
from app.routers import (
    auth,
    chat,
    conversations,
    diets,
    documents,
    metrics,
    preference,
    stats,
    workouts,
)

log = logging.getLogger("app")

_HTTP_ERR_CODE = {400: 40010, 401: 40100, 403: 40301, 404: 40401, 413: 41301, 502: 50202}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 一期简化：启动时建表。多实例/迁移需求出现后再引入 Alembic
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="jianshen-rag", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(workouts.router)
app.include_router(metrics.router)
app.include_router(diets.router)
app.include_router(preference.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(conversations.feedback_router)
app.include_router(stats.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    code = _HTTP_ERR_CODE.get(exc.status_code, 40010)
    return JSONResponse(status_code=exc.status_code, content=resp.fail(code, str(exc.detail)))


# Pydantic 校验失败的常见原因 → 中文提示（body 字段非法统一转 400，code 40010）
_VALIDATION_REASON = {
    "missing": "缺少必填字段",
    "date_from_datetime_parsing": "日期格式应为 YYYY-MM-DD",
    "date_parsing": "日期格式应为 YYYY-MM-DD",
    "datetime_from_date_parsing": "日期格式应为 YYYY-MM-DD",
    "float_parsing": "应为数字",
    "int_parsing": "应为整数",
    "bool_parsing": "应为布尔值",
    "greater_than": "数值必须大于 0",
    "greater_than_equal": "数值过小",
    "less_than_equal": "数值过大",
    "multiple_of": "数值不满足倍数要求",
    "string_too_short": "字符串过短",
    "string_too_long": "字符串过长",
    "too_short": "元素数量不足",
    "list_type": "应为数组",
    "string_type": "应为字符串",
    "dict_type": "应为对象",
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    loc = ".".join(
        str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path", "header")
    )
    reason = _VALIDATION_REASON.get(first.get("type", ""), first.get("msg", "参数格式错误"))
    message = f"{loc}: {reason}" if loc else reason
    return JSONResponse(status_code=400, content=resp.fail(40010, message))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    log.exception("未处理异常: %s", exc)
    return JSONResponse(status_code=500, content=resp.fail(50000, "系统错误"))