"""文档业务：上传/解析/切分/删除 的编排（D2），并同步维护向量索引（D4）。"""
import hashlib
import logging
import os
import shutil

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import config
from app.db import Document, User
from app.repositories import documents as documents_repo
from app.services import index, pipeline

log = logging.getLogger("app")

# 扩展名白名单：与 pipeline.load_texts 支持的解析器一一对应
_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".md", ".txt"}
# 文件头魔数：PDF / 老版 Word（OLE2 复合文档）/ docx（zip 容器）
_MAGIC = {
    ".pdf": (b"%PDF-",),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".docx": (b"PK\x03\x04",),
}


def _safe_filename(filename: str | None) -> str:
    """只保留文件名本身：剥离客户端可能携带的路径（防 ../ 与绝对路径穿越）。"""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:200] or "unnamed"


def _validate_upload(file: UploadFile, ext: str) -> None:
    """扩展名 ↔ 内容一致性校验：二进制格式查文件头魔数，文本格式按 UTF-8 试解码。"""
    if ext in _MAGIC:
        head = file.file.read(8192)
        file.file.seek(0)
        if not any(head.startswith(m) for m in _MAGIC[ext]):
            raise HTTPException(
                status_code=400, detail="文件内容与扩展名不符（文件可能已损坏或被改名）"
            )
        return
    raw = file.file.read()
    file.file.seek(0)
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文本文件需为 UTF-8 编码") from None


def _index_fail_reason(exc: Exception) -> str:
    """向量索引失败 → 可读 fail_reason（截到列宽 500）。"""
    return f"向量索引失败：{str(exc) or '未知错误'}"[:500]


def _md5(path: str) -> str:
    # hashlib.md5：对文件内容算指纹，用于秒传判定和最终文件名前缀
    h = hashlib.md5()
    with open(path, "rb") as f:
        # 按 1MB 分块迭代读取，避免大文件一次性读入内存
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _check_size(file: UploadFile) -> None:
    # seek 到末尾用 tell 取文件大小，再 seek(0) 复位，保证后续拷贝从头上开始
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB}MB 上限")


def create_document(
    db: Session, user: User, file: UploadFile, category: str, is_public: bool = False
) -> dict:
    _check_size(file)
    filename = _safe_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 PDF/Word/MD/TXT 格式")
    _validate_upload(file, ext)
    user_dir = os.path.join(config.UPLOAD_DIR, f"user_{user.id}")
    # makedirs(exist_ok=True)：按用户建立上传目录，已存在时静默通过
    os.makedirs(user_dir, exist_ok=True)
    tmp_path = os.path.join(user_dir, filename)
    with open(tmp_path, "wb") as out:
        # shutil.copyfileobj：以流式方式把上传内容分块写入磁盘，内存占用恒定
        shutil.copyfileobj(file.file, out)

    md5 = _md5(tmp_path)

    # 秒传：同用户同 MD5 且已就绪 → 直接引用
    existing = documents_repo.find_dedup(db, user.id, md5)
    if existing:
        os.remove(tmp_path)
        return _upload_out(existing, dedup=True)

    # 落定唯一文件名，避免覆盖
    final_path = os.path.join(user_dir, f"{md5}_{filename}")
    # 同名目标已在盘上（同 MD5 曾被上传过）就丢弃临时文件，否则原子 rename 落定
    if os.path.exists(final_path):
        os.remove(tmp_path)
    else:
        os.replace(tmp_path, final_path)

    doc = Document(
        user_id=user.id,
        filename=filename,
        file_md5=md5,
        size_bytes=os.path.getsize(final_path),
        category=category or "other",
        status="PROCESSING",
        is_public=is_public,
    )
    # 先入库拿到自增 id（Chroma 向量 id 前缀依赖它），状态置 PROCESSING 表示处理中
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 同步处理流水线（一期画线：不上队列）
    try:
        pages = pipeline.load_texts(final_path)
        chunks = pipeline.split_chunks(pages)
        # 切片先落盘：后续即便向量索引失败，原始切片仍可复用、便于排查
        pipeline.save_chunks(doc.id, doc.filename, doc.category, chunks)
        try:
            # 向量索引失败转 FAILED（不拖崩上传接口）；FAILED 分支不清索引
            index.index_document(
                doc.id, doc.filename, user.id, doc.category, chunks, is_public=doc.is_public
            )
        except Exception as e:
            log.warning("文档 %s 向量索引失败: %s", doc.id, e)
            doc.status = "FAILED"
            doc.fail_reason = _index_fail_reason(e)
        else:
            doc.status = "READY"
            doc.chunk_count = len(chunks)
            doc.fail_reason = None
        # 索引成功或失败都在这里统一提交状态变更
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
    # 统一在这里做 404/403 校验，避免各业务函数重复判断
    doc = documents_repo.get(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该文档")
    return doc


def list_documents(db: Session, user: User, category: str | None, page: int, size: int) -> dict:
    # 分页查询本人文档（category 可选过滤），再拼成前端约定的驼峰结构
    total, rows = documents_repo.page(db, user.id, category, page, size)
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
    # 按首传落定的命名规则（md5_原文件名）找回磁盘上的源文件
    path = os.path.join(config.UPLOAD_DIR, f"user_{user.id}", f"{doc.file_md5}_{doc.filename}")
    doc.status = "PROCESSING"
    db.commit()
    try:
        chunks = pipeline.split_chunks(pipeline.load_texts(path))
        # 覆盖写切片 JSON，保证磁盘上的切片与本次索引内容一致
        pipeline.save_chunks(doc.id, doc.filename, doc.category, chunks)
        try:
            # 重试成功：先清旧向量再重新索引（保证原子替换）
            index.remove_document(doc.id)
            index.index_document(
                doc.id, doc.filename, user.id, doc.category, chunks, is_public=doc.is_public
            )
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
        # os.remove：先删磁盘源文件；文件可能已被清理，忽略 FileNotFoundError 保证幂等
        os.remove(path)
    except FileNotFoundError:
        pass
    pipeline.remove_chunks(doc.id)
    # 三处同步：磁盘文件 + Chroma 向量（where doc_id）已删，业务记录最后删
    index.remove_document(doc.id)
    # 记录最后删：万一中途失败，还能凭记录找到残留的向量/文件做补偿
    db.delete(doc)
    db.commit()