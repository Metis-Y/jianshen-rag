"""只重建公共知识库（不动 demo 账号与训练/体征/饮食记录）。

用法（项目根目录）：
    ./.venv/Scripts/python.exe scripts/rebuild_public_kb.py

适用场景：往 samples/public/ 增删语料后，想快速让向量库与之一致，
又不想像 seed_demo.py 那样重置 demo 的记录数据。

- 清空 system 账号名下的全部公共资料（磁盘 + 切片 JSON + 向量 + 记录四处同步）
- 按 scripts/corpus_manifest.py 的清单重新上传 samples/public/ 下语料
- 每条语料走与接口一致的上传链路（解析 → 切分 → 向量化 → 落库）
- 结束后打印每篇的状态与切片数，便于核对
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import UploadFile  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import Document, SessionLocal, User  # noqa: E402
from app.services import document_service  # noqa: E402
from scripts.corpus_manifest import PUBLIC_CORPUS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(ROOT, "samples", "public")


def main() -> None:
    db = SessionLocal()
    try:
        sys_user = db.scalar(select(User).where(User.username == "system"))
        if sys_user is None:
            sys.exit("system 账号不存在，先跑 scripts/seed_demo.py")

        # 1) 清空旧公共资料（delete_document 内部同步清向量/切片/磁盘）
        old = db.scalars(select(Document).where(Document.user_id == sys_user.id)).all()
        for doc in old:
            document_service.delete_document(db, sys_user, doc.id)
        print(f"已清理旧公共资料 {len(old)} 份")

        # 2) 按清单重新上传
        total_chunks = 0
        failed: list[str] = []
        for name, category in PUBLIC_CORPUS:
            path = os.path.join(PUBLIC_DIR, name)
            if not os.path.exists(path):
                failed.append(f"{name}（文件缺失）")
                continue
            with open(path, "rb") as f:
                content = f.read()
            upload = UploadFile(file=io.BytesIO(content), filename=name)
            data = document_service.create_document(db, sys_user, upload, category, is_public=True)
            status = data["status"]
            chunks = data["chunkCount"] or 0
            total_chunks += chunks
            mark = "OK " if status == "READY" else "FAIL"
            print(f"[{mark}] {name:<28} chunks={chunks:<2} category={category}")
            if status != "READY":
                failed.append(f"{name}（{data['failReason']}）")

        print(f"\n公共知识库重建完成：{len(PUBLIC_CORPUS) - len(failed)}/{len(PUBLIC_CORPUS)} 份成功，"
              f"共 {total_chunks} 个切片")
        if failed:
            print("失败清单：" + "；".join(failed))
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
