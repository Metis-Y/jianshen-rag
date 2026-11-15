"""文档解析 + 切分流水线（D2）。重型 loader 在函数内延迟导入，保启动轻快。"""
import json
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import config

# 分隔符由粗到细：段落 → 换行 → 句号/感叹/问号 → 逗号 → 空格 → 空串（最后兜底硬切）
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "，", " ", ""]


def load_texts(path: str) -> list[dict]:
    """按扩展名解析文档，返回 [{page, text}]（页码尽力而为）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        # PyPDFLoader（底层 pypdf）：逐页提取文本，每页返回一个 Document
        docs = PyPDFLoader(path).load()
        # 页码按文档页序从 1 起；纯空白页丢弃，避免产生空切片
        return [
            {"page": i + 1, "text": d.page_content}
            for i, d in enumerate(docs)
            if d.page_content and d.page_content.strip()
        ]
    if ext in (".doc", ".docx"):
        from langchain_community.document_loaders import Docx2txtLoader

        # Docx2txtLoader（底层 python-docx）：抽取全部段落纯文本，无分页概念故 page=None
        return [{"page": None, "text": Docx2txtLoader(path).load()[0].page_content}]
    # md / txt / 其他一律按 UTF-8 文本读
    from langchain_community.document_loaders import TextLoader

    # TextLoader：整份文件按指定编码读成一个字符串（md/txt 通用）
    return [{"page": None, "text": TextLoader(path, encoding="utf-8").load()[0].page_content}]


def split_chunks(pages: list[dict]) -> list[dict]:
    """返回 [{seq, text, source}]。全文为空时抛 ValueError（扫描件场景）。"""
    # RecursiveCharacterTextSplitter：按分隔符优先级递归切分，尽量在语义边界断开
    # chunk_size 为单片字符上限；chunk_overlap 为相邻片重叠字符数，防止语义被拦腰截断
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=_SEPARATORS,
    )
    chunks: list[dict] = []
    seq = 0
    for page in pages:
        # split_text：切分单个字符串并返回字符串列表（不会生成 Document 对象）
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


# 切片 JSON 的落盘路径：data/chunks/{doc_id}.json，供重试与人工排查复用
def chunks_path(doc_id: int) -> str:
    return os.path.join(config.DATA_DIR, "chunks", f"{doc_id}.json")


def save_chunks(doc_id: int, doc_title: str, category: str, chunks: list[dict]) -> None:
    # makedirs(exist_ok=True)：确保 chunks 目录存在，重复创建不报错
    os.makedirs(os.path.dirname(chunks_path(doc_id)), exist_ok=True)
    with open(chunks_path(doc_id), "w", encoding="utf-8") as f:
        # json.dump + ensure_ascii=False：中文原文直写，不转义成 \uXXXX
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
        # os.remove：删除切片文件；文件可能本就不存在，吞掉 FileNotFoundError 保证幂等
        os.remove(chunks_path(doc_id))
    except FileNotFoundError:
        pass