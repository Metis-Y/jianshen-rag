"""文档解析 + 切分流水线（D2）。重型 loader 在函数内延迟导入，保启动轻快。"""
import json
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import config

_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "，", " ", ""]


def load_texts(path: str) -> list[dict]:
    """按扩展名解析文档，返回 [{page, text}]（页码尽力而为）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        docs = PyPDFLoader(path).load()
        return [
            {"page": i + 1, "text": d.page_content}
            for i, d in enumerate(docs)
            if d.page_content and d.page_content.strip()
        ]
    if ext in (".doc", ".docx"):
        from langchain_community.document_loaders import Docx2txtLoader

        return [{"page": None, "text": Docx2txtLoader(path).load()[0].page_content}]
    # md / txt / 其他一律按 UTF-8 文本读
    from langchain_community.document_loaders import TextLoader

    return [{"page": None, "text": TextLoader(path, encoding="utf-8").load()[0].page_content}]


def split_chunks(pages: list[dict]) -> list[dict]:
    """返回 [{seq, text, source}]。全文为空时抛 ValueError（扫描件场景）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=_SEPARATORS,
    )
    chunks: list[dict] = []
    seq = 0
    for page in pages:
        for piece in splitter.split_text(page["text"]):
            piece = piece.strip()
            if piece:
                chunks.append(
                    {"seq": seq, "text": piece, "source": f"第{page['page']}页" if page["page"] else ""}
                )
                seq += 1
    if not chunks:
        raise ValueError("无法提取文本（疑似扫描件或无文本内容）")
    return chunks


def chunks_path(doc_id: int) -> str:
    return os.path.join(config.DATA_DIR, "chunks", f"{doc_id}.json")


def save_chunks(doc_id: int, doc_title: str, category: str, chunks: list[dict]) -> None:
    os.makedirs(os.path.dirname(chunks_path(doc_id)), exist_ok=True)
    with open(chunks_path(doc_id), "w", encoding="utf-8") as f:
        json.dump(
            {"doc_id": doc_id, "doc_title": doc_title, "category": category, "chunks": chunks},
            f,
            ensure_ascii=False,
        )


def load_chunks(doc_id: int) -> dict:
    with open(chunks_path(doc_id), encoding="utf-8") as f:
        return json.load(f)


def remove_chunks(doc_id: int) -> None:
    try:
        os.remove(chunks_path(doc_id))
    except FileNotFoundError:
        pass