"""文档业务：上传/解析/切分/删除 的编排（D2），并同步维护向量索引（D4）。"""
import hashlib
import logging
import os
import shutil

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.db import Document, User
from app.services import index, pipeline

log = logging.getLogger("app")


def _index_fail_reason(exc: Exception) -> str:
    """向量索引失败 → 可读 fail_reason（截到列宽 500）。"""
    return f"向量索引失败：{str(exc) or '未知错误'}"[:500]


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _check_size(file: UploadFile) -> None:
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB}MB 上限")


def create_document(db: Session, user: User, file: UploadFile, category: str) -> dict:
    _check_size(file)
    user_dir = os.path.join(config.UPLOAD_DIR, f"user_{user.id}")
    os.makedirs(user_dir, exist_ok=True)
    tmp_path = os.path.join(user_dir, file.filename)
    with open(tmp_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    md5 = _md5(tmp_path)

    # 秒传：同用户同 MD5 且已就绪 → 直接引用
    existing = db.scalar(
        select(Document).where(
            Document.user_id == user.id,
            Document.file_md5 == md5,
            Document.status == "READY",
        )
    )
    if existing:
        os.remove(tmp_path)
        return _upload_out(existing, dedup=True)

    # 落定唯一文件名，避免覆盖
    final_path = os.path.join(user_dir, f"{md5}_{file.filename}")
    if os.path.exists(final_path):
        os.remove(tmp_path)
    else:
        os.replace(tmp_path, final_path)

    doc = Document(
        user_id=user.id,
        filename=file.filename,
        file_md5=md5,
        size_bytes=os.path.getsize(final_path),
        category=category or "other",
        status="PROCESSING",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 同步处理流水线（一期画线：不上队列）
    try:
        pages = pipeline.load_texts(final_path)
        chunks = pipeline.split_chunks(pages)
        pipeline.save_chunks(doc.id, doc.filename, doc.category, chunks)
        try:
            # 向量索引失败转 FAILED（不拖崩上传接口）；FAILED 分支不清索引
            index.index_document(doc.id, doc.filename, user.id, doc.category, chunks)
        except Exception as e:
            log.warning("文档 %s 向量索引失败: %s", doc.id, e)
            doc.status = "FAILED"
            doc.fail_reason = _index_fail_reason(e)
        else:
            doc.status = "READY"
            doc.chunk_count = len(chunks)
            doc.fail_reason = None
        db.commit()
    except Exception as e:  # 解析失败：给用户可读原因
        doc.status = "FAILED"
        doc.fail_reason = str(e) or "解析失败"
        db.commit()
    db.refresh(doc)
    return _upload_out(doc, dedup=False)


def _upload_out(doc: Document, dedup: bool) -> dict:
    return {
        "docId": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "chunkCount": doc.chunk_count,
        "failReason": doc.fail_reason,
        "dedup": dedup,
    }


def _get_owned(db: Session, user_id: int, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该文档")
    return doc


def list_documents(db: Session, user: User, category: str | None, page: int, size: int) -> dict:
    stmt = select(Document).where(Document.user_id == user.id)
    if category:
        stmt = stmt.where(Document.category == category)
    stmt = stmt.order_by(Document.id.desc()).offset((page - 1) * size).limit(size)
    rows = db.scalars(stmt).all()
    total = len(db.scalars(select(Document).where(Document.user_id == user.id)).all())
    return {
        "total": total,
        "page": page,
        "size": size,
        "list": [
            {
                "docId": d.id,
                "filename": d.filename,
                "category": d.category,
                "status": d.status,
                "chunkCount": d.chunk_count,
                "sizeBytes": d.size_bytes,
                "failReason": d.fail_reason,
                "createdAt": d.created_at.isoformat(),
            }
            for d in rows
        ],
    }


def retry_document(db: Session, user: User, doc_id: int) -> dict:
    doc = _get_owned(db, user.id, doc_id)
    path = os.path.join(config.UPLOAD_DIR, f"user_{user.id}", f"{doc.file_md5}_{doc.filename}")
    doc.status = "PROCESSING"
    db.commit()
    try:
        chunks = pipeline.split_chunks(pipeline.load_texts(path))
        pipeline.save_chunks(doc.id, doc.filename, doc.category, chunks)
        try:
            # 重试成功：先清旧向量再重新索引（保证原子替换）
            index.remove_document(doc.id)
            index.index_document(doc.id, doc.filename, user.id, doc.category, chunks)
        except Exception as e:
            log.warning("文档 %s 重试向量索引失败: %s", doc.id, e)
            doc.status = "FAILED"
            doc.fail_reason = _index_fail_reason(e)
        else:
            doc.status = "READY"
            doc.chunk_count = len(chunks)
            doc.fail_reason = None
    except Exception as e:
        doc.status = "FAILED"
        doc.fail_reason = str(e) or "解析失败"
    db.commit()
    db.refresh(doc)
    return _upload_out(doc, dedup=False)


def delete_document(db: Session, user: User, doc_id: int) -> None:
    doc = _get_owned(db, user.id, doc_id)
    path = os.path.join(config.UPLOAD_DIR, f"user_{user.id}", f"{doc.file_md5}_{doc.filename}")
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    pipeline.remove_chunks(doc.id)
    # 三处同步：磁盘文件 + Chroma 向量（where doc_id）已删，业务记录最后删
    index.remove_document(doc.id)
    db.delete(doc)
    db.commit()