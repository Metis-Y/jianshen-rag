"""应用入口：路由、生命周期、全局异常转包络。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import resp
from app.db import Base, engine
from app.routers import auth

log = logging.getLogger("app")

_HTTP_ERR_CODE = {400: 40010, 401: 40100, 403: 40301, 404: 40401, 413: 41301, 502: 50202}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 一期简化：启动时建表。多实例/迁移需求出现后再引入 Alembic
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="jianshen-rag", lifespan=lifespan)
app.include_router(auth.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    code = _HTTP_ERR_CODE.get(exc.status_code, 40010)
    return JSONResponse(status_code=exc.status_code, content=resp.fail(code, str(exc.detail)))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    log.exception("未处理异常: %s", exc)
    return JSONResponse(status_code=500, content=resp.fail(50000, "系统错误"))