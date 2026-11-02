"""文档路由（docs/05 契约）。"""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app import resp
from app.auth import get_current_user
from app.db import User, get_db
from app.services import document_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("")
def upload(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = document_service.create_document(db, user, file, category)
    return resp.ok(data)


@router.get("")
def list_docs(
    category: str | None = None,
    page: int = 1,
    size: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp.ok(document_service.list_documents(db, user, category, page, size))


@router.get("/{doc_id}")
def detail(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = document_service.list_documents(db, user, None, 1, 1000)["list"]
    hit = next((d for d in data if d["docId"] == doc_id), None)
    if hit is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="文档不存在")
    return resp.ok(hit)


@router.post("/{doc_id}/retry")
def retry(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resp.ok(document_service.retry_document(db, user, doc_id))


@router.delete("/{doc_id}")
def delete(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document_service.delete_document(db, user, doc_id)
    return resp.ok()