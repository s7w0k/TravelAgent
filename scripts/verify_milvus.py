"""Milvus Lite 混合检索验证脚本。"""

import asyncio

from backend.config import get_settings
from backend.rag.retriever import get_retriever


async def main() -> None:
    settings = get_settings()
    retriever = get_retriever()

    print("=== Travel Agent Milvus Lite 验证 ===")
    print(f"向量后端: {settings.RAG_VECTOR_BACKEND}")
    print(f"Milvus Lite DB: {settings.MILVUS_LITE_PATH}")

    health = retriever.vector_store.health_check()
    print("\n[1] 向量后端健康检查")
    print(health)
    if not health.get("healthy"):
        raise SystemExit("Milvus Lite 未就绪，请先检查依赖、路径和配置")

    print("\n[2] 写入测试文档")
    await retriever.add_document(
        content="苏州园林经典玩法包括拙政园、留园、平江路和苏州博物馆，适合 2 到 3 天慢游。",
        title="苏州园林慢游攻略",
        source="全网",
        metadata={"city": "苏州", "theme": "园林"},
    )
    await retriever.add_document(
        content="上海到苏州高铁通常 30 分钟左右可达，周末短途出游非常方便。",
        title="上海到苏州交通建议",
        source="小红书",
        metadata={"city": "苏州", "theme": "交通"},
    )
    print("测试文档写入完成")

    print("\n[3] 执行混合检索")
    results = await retriever.retrieve(query="苏州园林两日游", top_k=3)
    for index, result in enumerate(results, 1):
        print(f"{index}. {result.title} | {result.source} | distance={result.distance}")
        print(f"   metadata={result.metadata}")
        print(f"   content={result.content[:80]}...")

    print("\n验证完成")


if __name__ == "__main__":
    asyncio.run(main())
