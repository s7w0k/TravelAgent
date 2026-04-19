"""向量存储模块，使用 ChromaDB 本地持久化。"""

from typing import Any, Dict, List, Optional

import chromadb

from backend.config import get_settings
from backend.logger import get_logger
from backend.rag.embedding_service import get_embedding_service

logger = get_logger(__name__)
settings = get_settings()


class VectorStore:
    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        self.persist_dir = settings.CHROMA_PERSIST_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(name=self.collection_name)

    def _normalize_metadata(self, metadata: dict) -> dict:
        meta = dict(metadata or {})
        normalized = {
            **meta,
            "source": str(meta.get("source", "未知")),
            "title": str(meta.get("title", "")),
            "doc_id": str(meta.get("doc_id", "")),
            "chunk_index": int(meta.get("chunk_index", 0) or 0),
        }
        for key, value in list(normalized.items()):
            if value is None:
                normalized[key] = ""
            elif isinstance(value, (list, dict, tuple, set)):
                normalized[key] = str(value)
            elif not isinstance(value, (str, int, float, bool)):
                normalized[key] = str(value)
        return normalized

    def _convert_filter(self, filter: Optional[dict]) -> Optional[dict]:
        if not filter or not isinstance(filter, dict):
            return None
        source_filter = filter.get("source")
        if isinstance(source_filter, dict) and "$in" in source_filter:
            values = [str(v) for v in source_filter.get("$in") or []]
            if not values:
                return None
            if len(values) == 1:
                return {"source": values[0]}
            return {"$or": [{"source": value} for value in values]}
        return None

    async def add_documents(self, texts: List[str], metadatas: List[dict], ids: Optional[List[str]] = None) -> bool:
        if not texts:
            return True
        try:
            embeddings = await get_embedding_service().embed_texts(texts)
            ids = ids or [f"doc_{i}_{abs(hash(text))}" for i, text in enumerate(texts)]
            normalized_metadatas = [self._normalize_metadata(metadatas[i] if i < len(metadatas) else {}) for i in range(len(texts))]
            self._collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=normalized_metadatas)
            logger.info(f"成功添加 {len(texts)} 个文档到 ChromaDB")
            return True
        except Exception as e:
            logger.error(f"ChromaDB 添加文档失败: {e}")
            return False

    async def search(self, query: str, top_k: int = None, filter: Optional[dict] = None) -> List[Dict[str, Any]]:
        top_k = top_k or settings.RAG_TOP_K
        try:
            query_embedding = await get_embedding_service().embed_text(query)
            kwargs: Dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            where = self._convert_filter(filter)
            if where:
                kwargs["where"] = where
            results = self._collection.query(**kwargs)
            docs: List[Dict[str, Any]] = []
            ids = results.get("ids", [[]])[0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            for i in range(len(ids)):
                docs.append(
                    {
                        "id": ids[i],
                        "content": documents[i] if i < len(documents) else "",
                        "metadata": metadatas[i] if i < len(metadatas) and metadatas[i] else {},
                        "distance": distances[i] if i < len(distances) else 1.0,
                    }
                )
            return docs
        except Exception as e:
            logger.error(f"ChromaDB 搜索失败: {e}")
            return []

    async def delete_by_id(self, ids: List[str]) -> bool:
        try:
            if not ids:
                return True
            self._collection.delete(ids=ids)
            return True
        except Exception as e:
            logger.error(f"ChromaDB 删除文档失败: {e}")
            return False

    async def delete_by_metadata(self, filter: dict) -> bool:
        try:
            where = self._convert_filter(filter)
            if where:
                self._collection.delete(where=where)
            return True
        except Exception as e:
            logger.error(f"ChromaDB 根据元数据删除失败: {e}")
            return False

    def get_collection_info(self) -> dict:
        try:
            count = self._collection.count()
            return {
                "name": self.collection_name,
                "count": count,
                "persist_dir": str(self.persist_dir),
                "backend": "chroma",
            }
        except Exception as e:
            logger.error(f"获取 ChromaDB 集合信息失败: {e}")
            return {
                "name": self.collection_name,
                "count": 0,
                "persist_dir": str(self.persist_dir),
                "backend": "chroma",
            }

    def health_check(self) -> dict:
        try:
            count = self._collection.count()
            return {
                "backend": "chroma",
                "healthy": True,
                "collection_name": self.collection_name,
                "document_count": count,
                "detail": f"ChromaDB ok: {self.persist_dir}",
            }
        except Exception as e:
            logger.error(f"ChromaDB 健康检查失败: {e}")
            return {
                "backend": "chroma",
                "healthy": False,
                "collection_name": self.collection_name,
                "document_count": 0,
                "detail": str(e),
            }

    def reset(self) -> bool:
        try:
            self._client.delete_collection(name=self.collection_name)
            self._collection = self._client.get_or_create_collection(name=self.collection_name)
            return True
        except Exception as e:
            logger.error(f"重置 ChromaDB 向量库失败: {e}")
            return False


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
        logger.info("当前向量后端: chroma")
    return _vector_store
