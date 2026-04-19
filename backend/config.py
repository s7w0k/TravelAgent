"""
配置管理模块
集中管理所有配置项
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from langchain_community.embeddings import TextEmbedEmbeddings

# 启动时加载环境变量
from dotenv import load_dotenv
root_dir = Path(__file__).parent.parent
env_file = root_dir / ".env"
if env_file.exists():
    load_dotenv(env_file, override=True)


class Settings(BaseModel):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "Travel Agent API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # API 密钥 - 从环境变量读取
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DASHSCOPE_API_KEY: Optional[str] = os.getenv("DASHSCOPE_API_KEY")
    AMAP_MAPS_API_KEY: Optional[str] = os.getenv("AMAP_MAPS_API_KEY")

    # 豆包 Seedream 图像生成配置
    SEEDREAM_API_KEY: Optional[str] = os.getenv("SEEDREAM_API_KEY")
    SEEDREAM_BASE_URL: str = os.getenv("SEEDREAM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

    # Agent 配置
    RECURSION_LIMIT: int = 25
    MAX_CONVERSATION_HISTORY: int = 20
    MAX_INPUT_LENGTH: int = 200
    MAX_OUTPUT_LENGTH: int = 300
    ENABLE_SESSION_PERSISTENCE: bool = True
    ENABLE_LONG_TERM_MEMORY: bool = True
    ENABLE_DYNAMIC_SUMMARY: bool = True
    ENABLE_CONTEXT_COMPRESSION: bool = True
    CONTEXT_WINDOW_MESSAGES: int = 8
    SESSION_MEMORY_DIR: Path = Field(default_factory=lambda: root_dir / "data" / "session_memory")

    # RAG 配置
    RAG_VECTOR_BACKEND: str = "chroma"
    RAG_EMBEDDING_MODEL: str = "text-embedding-v4"
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 3
    RAG_COLLECTION_NAME: str = "travel_knowledge"
    RAG_ENABLE_HYBRID: bool = True
    RAG_ENABLE_QUERY_REWRITE: bool = True
    RAG_ENABLE_RERANK: bool = True
    RAG_ENABLE_CONSTRAINT_FILTER: bool = True
    RAG_RETRIEVAL_EXPAND_FACTOR: int = 3
    RAG_VECTOR_WEIGHT: float = 0.65
    RAG_KEYWORD_WEIGHT: float = 0.35
    RAG_KEYWORD_TOP_K: int = 8
    RAG_BM25_K1: float = 1.5
    RAG_BM25_B: float = 0.75

    # Chroma 配置
    CHROMA_PERSIST_DIR: Path = Field(default_factory=lambda: Path(os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")))
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "travel_knowledge")

    # Milvus Lite 配置
    MILVUS_LITE_PATH: Path = Field(default_factory=lambda: Path(os.getenv("MILVUS_LITE_PATH", "./data/milvus_lite.db")))
    MILVUS_COLLECTION_NAME: str = os.getenv("MILVUS_COLLECTION_NAME", "travel_knowledge")
    MILVUS_VECTOR_DIM: int = int(os.getenv("MILVUS_VECTOR_DIM", "1536"))
    MILVUS_METRIC_TYPE: str = os.getenv("MILVUS_METRIC_TYPE", "COSINE")

    # 知识库配置
    KNOWLEDGE_BASE_DIR: Path = Field(default_factory=lambda: Path("./data/knowledge_base"))
    KNOWLEDGE_RAW_DIR: Path = Field(default_factory=lambda: Path("./data/knowledge_base/raw"))
    KNOWLEDGE_PROCESSED_DIR: Path = Field(default_factory=lambda: Path("./data/knowledge_base/processed"))

    # CORS 配置
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: list[str] = Field(default_factory=lambda: ["*"])

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
