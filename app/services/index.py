"""Chroma 向量索引（D3/D4）：文档碎片 入索引 / 出索引 / 检索。

集合 `kb_main` 在模块导入（应用启动）时 get_or_create，索引结构用 Chroma 默认 HNSW；
embedding 走 OpenAI 兼容接口（config.EMBEDDING_*），向量为单精度维度序列，
Chroma 只存向量 + 明文 + metadata（值仅 str/int，不含 None）。
"""
import logging

import chromadb
from chromadb.config import Settings
from openai import OpenAI

from app import config

log = logging.getLogger("app")

_COLLECTION_NAME = "kb_main"
_EMBED_BATCH = 32          # embedding 请求批量上限兜底（硅基流动等平台的稳定批量）
_META_TEXT_MAX = 200       # 元数据文本截断，避免超长文件名/来源撑爆 Chroma 元数据

_client = chromadb.PersistentClient(
    path=config.CHROMA_DB_PATH,
    settings=Settings(anonymized_telemetry=False),
)
_collection = _client.get_or_create_collection(
    name=_COLLECTION_NAME,
    embedding_function=None,  # 向量外部生成，禁用内置 download-on-demand 模型
)

_embed_client: OpenAI | None = None


def _embed_client_get() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(
            api_key=config.EMBEDDING_API_KEY,
            base_url=config.EMBEDDING_BASE_URL,
        )
    return _embed_client


def _embed(texts: list[str]) -> list[list[float]]:
    """OpenAI 兼容 embedding 批量向量化，返回与输入等长的向量列表（保持顺序）。"""
    if not config.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 未配置")
    client = _embed_client_get()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i : i + _EMBED_BATCH]
        resp = client.embeddings.create(model=config.EMBEDDING_MODEL, input=batch)
        vectors.extend(item.embedding for item in resp.data)
    return vectors


def _meta(
    doc_id: int,
    doc_title: str,
    owner_id: int,
    category: str,
    seq: int,
    source: str,
    is_public: bool = False,
) -> dict:
    """metadata 值只允许 str/int/bool（Chroma 要求，None 会抛错）。"""
    return {
        "doc_id": int(doc_id),
        "doc_title": (doc_title or "")[:_META_TEXT_MAX],
        "owner_id": int(owner_id),
        "seq": int(seq),
        "source": (source or "")[:_META_TEXT_MAX],
        "category": (category or "other")[:16],
        "is_public": bool(is_public),
    }


def index_document(
    doc_id: int,
    doc_title: str,
    owner_id: int,
    category: str,
    chunks: list[dict],
    is_public: bool = False,
) -> None:
    """文档全量碎片向量化后写入集合；ids 用 `{doc_id}:{seq}` 唯一标识。"""
    if not chunks:
        return
    texts = [str(c["text"]) for c in chunks]
    vectors = _embed(texts)
    # 先删后加可保证同名 id 幂等；上传是新 doc_id，重试前已显式 remove，此处等价防重
    _collection.add(
        ids=[f"{doc_id}:{c['seq']}" for c in chunks],
        embeddings=vectors,
        documents=texts,
        metadatas=[
            _meta(doc_id, doc_title, owner_id, category, c["seq"], c.get("source", ""), is_public)
            for c in chunks
        ],
    )


def remove_document(doc_id: int) -> None:
    """删除某文档的全部向量（where doc_id 匹配）。"""
    _collection.delete(where={"doc_id": int(doc_id)})


def retrieve(
    owner_id: int,
    question: str,
    top_k: int = config.TOPK,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """私有向量检索：默认全库（本人文档）；document_ids 非空时限定文档范围。

    返回按相似度排序的 [{doc_id, doc_title, seq, source, text}]（text 取明文）。
    """
    # 可见集合：本人文档 + 公共知识库文档
    base: dict = {
        "$or": [
            {"owner_id": int(owner_id)},
            {"is_public": True},
        ]
    }
    if document_ids:  # 非空列表 → 可见集合内再限定文档白名单
        where: dict = {
            "$and": [
                base,
                {"doc_id": {"$in": [int(i) for i in document_ids]}},
            ]
        }
    else:
        where = base

    # 向量化 question（embedding 维度直接透传，无特殊处理）
    query_vec = _embed([question])[0]
    result = _collection.query(
        query_embeddings=[query_vec],
        n_results=int(top_k),
        where=where,
    )

    ids = result.get("ids") or [[]]
    metas = result.get("metadatas") or [[]]
    docs = result.get("documents") or [[]]

    hits: list[dict] = []
    for i, meta in enumerate(metas[0]):
        hits.append(
            {
                "doc_id": meta.get("doc_id"),
                "doc_title": (meta.get("doc_title") or ""),
                "seq": meta.get("seq", 0),
                "source": (meta.get("source") or ""),
                "text": docs[0][i] if i < len(docs[0]) else "",
            }
        )
    return hits