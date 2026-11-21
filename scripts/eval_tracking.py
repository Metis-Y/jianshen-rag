"""评测 run 持久化：MLflow 本地 file backend。

对齐 MLflow 的 run(参数 + 指标 + 产物) 模型：跑完一次评测，把配置(params)、
分数(metrics)、标签(tags)与逐题产物(artifact)记成一条不可变记录，
`mlflow ui` 一条命令打开历史对比面板。

说明：MLflow 只"存 + 显示"，不替跑评估、不抓 LLM 调用过程（后者是 Langfuse 的活，
本阶段不引）。
"""
import hashlib
import os
import subprocess

import mlflow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENT = "fitpal-eval"


def init_tracking() -> None:
    """本地 SQLite 后端 + 固定实验名；重复调用保持同一批 run 落同一实验。

    注：MLflow 3.x 已把文件后端（mlruns/）标为维护模式，默认抛错，故改用 SQLite。
    """
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment(EXPERIMENT)


def git_commit() -> str:
    """当前 git 短 commit（非 git 环境或失败时返回空串）。"""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return ""


def file_sha256(path: str) -> str:
    """文件内容 sha256 前 12 位，用作题库 / 语料清单的版本指纹。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()[:12]
    except OSError:
        return ""


def log_run(run_name: str, params: dict, metrics: dict, tags: dict, artifact_path: str):
    """开始一次 run → log 参数/指标/标签/产物 → end（异常也保证 end 并上抛）。"""
    run = mlflow.start_run(run_name=run_name)
    try:
        if params:
            mlflow.log_params(params)
        if metrics:
            mlflow.log_metrics(metrics)
        if tags:
            mlflow.set_tags(tags)
        if artifact_path and os.path.exists(artifact_path):
            mlflow.log_artifact(artifact_path)
    finally:
        mlflow.end_run()
    return run