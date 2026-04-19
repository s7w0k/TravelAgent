"""
关键词检索器模块
基于 processed 文档构建轻量 BM25 索引，提供关键词召回能力
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import get_settings
from backend.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class KeywordSearchResult:
    """关键词检索结果"""

    content: str
    source: str
    title: str
    score: float
    metadata: Dict[str, Any]
    doc_id: str
    chunk_id: str
    chunk_index: int


@dataclass
class _KeywordDoc:
    """BM25 内部文档结构"""

    content: str
    source: str
    title: str
    metadata: Dict[str, Any]
    doc_id: str
    chunk_id: str
    chunk_index: int
    tokens: List[str]
    term_freqs: Dict[str, int]
    length: int


class KeywordRetriever:
    """基于本地 processed 文档的轻量 BM25 检索器"""

    def __init__(self):
        self.processed_dir: Path = settings.KNOWLEDGE_PROCESSED_DIR
        self.k1 = settings.RAG_BM25_K1
        self.b = settings.RAG_BM25_B
        self._docs: List[_KeywordDoc] = []
        self._doc_freqs: Dict[str, int] = {}
        self._avg_doc_len: float = 0.0
        self._source_index: Dict[str, List[int]] = {}
        self._snapshot: Optional[tuple[int, float]] = None

    def _tokenize(self, text: str) -> List[str]:
        """轻量 token 化：英文按词，中文按单字"""
        if not text:
            return []

        text = text.lower()
        tokens: List[str] = []

        # 英文和数字词
        tokens.extend(re.findall(r"[a-z0-9]+", text))

        # 中文单字
        tokens.extend(re.findall(r"[\u4e00-\u9fff]", text))

        return [token for token in tokens if token.strip()]

    def _build_snapshot(self) -> tuple[int, float]:
        if not self.processed_dir.exists():
            return (0, 0.0)

        files = list(self.processed_dir.glob("*.json"))
        if not files:
            return (0, 0.0)

        latest_mtime = max(file.stat().st_mtime for file in files)
        return (len(files), latest_mtime)

    def _should_refresh(self) -> bool:
        current_snapshot = self._build_snapshot()
        return current_snapshot != self._snapshot

    def _load_index(self) -> None:
        """构建 BM25 索引"""
        self._docs = []
        self._doc_freqs = {}
        self._source_index = {}
        self._avg_doc_len = 0.0

        if not self.processed_dir.exists():
            logger.info("processed 文档目录不存在，跳过关键词索引构建")
            self._snapshot = (0, 0.0)
            return

        total_length = 0
        file_count = 0

        for file_path in sorted(self.processed_dir.glob("*.json")):
            file_count += 1
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"读取 processed 文档失败: {file_path}, error={e}")
                continue

            doc_id = data.get("doc_id", file_path.stem)
            title = data.get("title", "")
            source = data.get("source", "未知")
            chunks = data.get("chunks", [])

            for chunk in chunks:
                content = chunk.get("content", "")
                metadata = chunk.get("metadata", {}) or {}
                chunk_id = chunk.get("chunk_id", "")
                chunk_index = chunk.get("index", metadata.get("chunk_index", 0))

                joined_text = f"{title}\n{content}\n{source}"
                tokens = self._tokenize(joined_text)
                if not tokens:
                    continue

                term_freqs: Dict[str, int] = {}
                unique_tokens = set()
                for token in tokens:
                    term_freqs[token] = term_freqs.get(token, 0) + 1
                    unique_tokens.add(token)

                keyword_doc = _KeywordDoc(
                    content=content,
                    source=source,
                    title=title,
                    metadata=metadata,
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    chunk_index=int(chunk_index or 0),
                    tokens=tokens,
                    term_freqs=term_freqs,
                    length=len(tokens),
                )
                self._docs.append(keyword_doc)
                total_length += keyword_doc.length

                normalized_source = source.lower()
                self._source_index.setdefault(normalized_source, []).append(len(self._docs) - 1)

                for token in unique_tokens:
                    self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1

        self._avg_doc_len = total_length / len(self._docs) if self._docs else 0.0
        self._snapshot = self._build_snapshot()
        logger.info(
            f"关键词索引构建完成: files={file_count}, chunks={len(self._docs)}, avg_len={self._avg_doc_len:.2f}"
        )

    def _ensure_index(self) -> None:
        if not self._docs or self._should_refresh():
            self._load_index()

    def _idf(self, token: str) -> float:
        doc_freq = self._doc_freqs.get(token, 0)
        doc_count = len(self._docs)
        if doc_count == 0:
            return 0.0
        return math.log(1 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))

    def _score_doc(self, doc: _KeywordDoc, query_tokens: List[str]) -> float:
        if not query_tokens or doc.length == 0 or self._avg_doc_len == 0:
            return 0.0

        score = 0.0
        for token in query_tokens:
            term_freq = doc.term_freqs.get(token, 0)
            if term_freq == 0:
                continue

            idf = self._idf(token)
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (1 - self.b + self.b * doc.length / self._avg_doc_len)
            score += idf * numerator / denominator

        return score

    def search(
        self,
        query: str,
        top_k: int = 5,
        sources: Optional[List[str]] = None,
    ) -> List[KeywordSearchResult]:
        """执行关键词检索"""
        self._ensure_index()

        if not self._docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        allowed_sources = None
        if sources:
            allowed_sources = {source.lower() for source in sources}

        scored_docs: List[tuple[float, _KeywordDoc]] = []
        for doc in self._docs:
            if allowed_sources and doc.source.lower() not in allowed_sources:
                continue

            score = self._score_doc(doc, query_tokens)
            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda item: item[0], reverse=True)
        top_results = scored_docs[:top_k]

        return [
            KeywordSearchResult(
                content=doc.content,
                source=doc.source,
                title=doc.title,
                score=score,
                metadata=doc.metadata,
                doc_id=doc.doc_id,
                chunk_id=doc.chunk_id,
                chunk_index=doc.chunk_index,
            )
            for score, doc in top_results
        ]


_keyword_retriever: Optional[KeywordRetriever] = None


def get_keyword_retriever() -> KeywordRetriever:
    """获取关键词检索器全局实例"""
    global _keyword_retriever
    if _keyword_retriever is None:
        _keyword_retriever = KeywordRetriever()
    return _keyword_retriever
