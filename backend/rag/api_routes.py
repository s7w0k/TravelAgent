"""
RAG API 路由模块
提供知识库管理的 REST API
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logger import get_logger
from backend.rag.retriever import get_retriever

logger = get_logger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])


class AddDocumentRequest(BaseModel):
    """添加文档请求"""
    content: str
    title: str
    source: str = "全网"
    metadata: Optional[dict] = None


class AddDocumentResponse(BaseModel):
    """添加文档响应"""
    success: bool
    doc_id: str
    chunk_count: int
    message: str


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str
    top_k: int = 3
    sources: Optional[List[str]] = None


class SearchResponse(BaseModel):
    """搜索响应"""
    results: List[dict]
    total: int


class KnowledgeStatsResponse(BaseModel):
    """知识库统计响应"""
    collection_name: str
    document_count: int
    persist_dir: str
    chunk_size: int
    chunk_overlap: int


class VectorHealthResponse(BaseModel):
    """向量后端健康检查响应"""
    backend: str
    healthy: bool
    collection_name: str
    document_count: int
    detail: str


@router.post("/documents", response_model=AddDocumentResponse)
async def add_document(request: AddDocumentRequest):
    """添加文档到知识库"""
    try:
        retriever = get_retriever()
        success = await retriever.add_document(
            content=request.content,
            title=request.title,
            source=request.source,
            metadata=request.metadata,
        )
        if success:
            return AddDocumentResponse(success=True, doc_id="", chunk_count=0, message="文档添加成功")
        raise HTTPException(status_code=500, detail="文档添加失败")
    except Exception as e:
        logger.error(f"添加文档 API 错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """搜索知识库"""
    try:
        retriever = get_retriever()
        results = await retriever.retrieve(query=request.query, top_k=request.top_k, sources=request.sources)
        results_data = [
            {
                "content": result.content,
                "source": result.source,
                "title": result.title,
                "distance": result.distance,
                "metadata": result.metadata,
            }
            for result in results
        ]
        return SearchResponse(results=results_data, total=len(results_data))
    except Exception as e:
        logger.error(f"搜索 API 错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/xiaohongshu", response_model=SearchResponse)
async def search_xiaohongshu(request: SearchRequest):
    """搜索小红书内容"""
    try:
        retriever = get_retriever()
        results = await retriever.retrieve_xiaohongshu(query=request.query, top_k=request.top_k)
        results_data = [
            {
                "content": result.content,
                "source": result.source,
                "title": result.title,
                "distance": result.distance,
                "metadata": result.metadata,
            }
            for result in results
        ]
        return SearchResponse(results=results_data, total=len(results_data))
    except Exception as e:
        logger.error(f"搜索小红书 API 错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=KnowledgeStatsResponse)
async def get_knowledge_stats():
    """获取知识库统计信息"""
    try:
        retriever = get_retriever()
        stats = retriever.get_knowledge_stats()
        if not stats:
            raise HTTPException(status_code=500, detail="无法获取统计信息")
        return KnowledgeStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"统计 API 错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector/health", response_model=VectorHealthResponse)
async def get_vector_health():
    """获取当前向量后端健康状态"""
    try:
        retriever = get_retriever()
        health = retriever.vector_store.health_check()
        return VectorHealthResponse(**health)
    except Exception as e:
        logger.error(f"向量后端健康检查错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
