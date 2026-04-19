# 混合检索引擎升级实现方案

## 1. 目标说明

本方案针对 `需求文档 1：混合检索引擎升级（Milvus + BM25 + Hybrid RAG）`，结合当前项目现状，给出一套**基于现有代码可落地、可运行、改动范围可控**的实施方案。

当前项目的现实基础如下：

- 已有向量检索能力，历史底层实现为 `Chroma`
- 已有文档清洗、分块、向量入库流程
- 已有统一检索入口 `Retriever`
- 已有 RAG API 与 SearchAgent 调用链路
- 已补充本地 BM25 关键词检索器
- 当前目标是进一步接入 `Milvus`，实现真正的 `Milvus + BM25 + Hybrid RAG`

因此，本次实现遵循以下原则：

1. **优先保证现有系统稳定运行**
2. **不大规模重构无关模块**
3. **将向量存储层改造成可切换架构**
4. **默认支持 Milvus 配置接入，同时保留 Chroma 回退能力**

---

## 2. 实施策略

### 阶段一：已完成能力

当前已完成：

- 本地轻量 BM25 关键词召回器
- `Retriever` 中的 Hybrid Retrieval 融合逻辑
- 检索结果去重与统一排序

### 阶段二：本次实施重点

本次重点实现：

- 将 `VectorStore` 从单一 Chroma 实现升级为可切换存储层
- 新增 `MilvusVectorStore`
- 通过配置选择 `milvus` 或 `chroma`
- 保持现有 `Retriever` / `RAG API` / `SearchAgent` 接口不变
- 让现有 BM25 与 Milvus 向量召回共同组成 Hybrid Retrieval

### 阶段三：后续增强

后续还可以继续补充：

- Query Rewrite
- 目的地 / 天数 / 预算元数据过滤
- Rerank 重排
- 热门 query 缓存
- Milvus 高级索引与分区优化

---

## 3. 现有代码结构分析

### 3.1 `backend/rag/document_processor.py`
负责：
- 文档原始保存
- 内容清洗
- 文档分块

可复用点：
- `processed/*.json` 已保留 chunk 级别文本与 metadata，可直接作为 BM25 数据源
- 分块生成的 `chunk_id` 可直接作为向量主键

### 3.2 `backend/rag/vector_store.py`
负责：
- 向量入库
- 向量搜索
- 删除与统计

本次会将其升级为统一入口，并新增 Milvus 后端实现。

### 3.3 `backend/rag/retriever.py`
负责：
- 统一检索入口
- 检索结果输出
- 向量召回 + BM25 融合

本次尽量不改其对上层的接口，只让底层向量召回来源切换为可配置后端。

### 3.4 `backend/rag/api_routes.py`
负责：
- 对外暴露 RAG 检索接口

原则上无需改请求结构。

---

## 4. 总体架构

```text
用户 Query
   │
   ▼
Retriever
   ├── Vector Retrieval（Milvus / Chroma）
   ├── Keyword Retrieval（BM25）
   ├── Result Merge
   ├── Deduplicate
   └── Unified Ranking
        ▼
   SearchResult[]
```

其中：

- 向量后端由配置项决定
- Hybrid Retrieval 始终通过统一 `Retriever` 输出结果

---

## 5. Milvus 接入设计

## 5.1 新增向量后端抽象思路

不对上层暴露 Milvus 细节，而是在 `vector_store.py` 中统一封装：

- `ChromaVectorStore`
- `MilvusVectorStore`
- `get_vector_store()` 根据配置返回实例

这样可以保证：

- 上层无需改调用方式
- 出问题时可以回退到 Chroma
- 后续便于做 A/B 或本地开发切换

---

## 5.2 Milvus 配置项设计

在 `backend/config.py` 中新增：

- `RAG_VECTOR_BACKEND: str = "milvus"`
- `MILVUS_URI: str = "http://127.0.0.1:19530"`
- `MILVUS_TOKEN: Optional[str]`
- `MILVUS_DB_NAME: str = "default"`
- `MILVUS_COLLECTION_NAME: str = "travel_knowledge"`
- `MILVUS_VECTOR_DIM: int = 1536`
- `MILVUS_INDEX_TYPE: str = "AUTOINDEX"`
- `MILVUS_METRIC_TYPE: str = "COSINE"`
- `MILVUS_CONSISTENCY_LEVEL: str = "Bounded"`

### 配置说明

- `RAG_VECTOR_BACKEND`：控制当前向量后端
- `MILVUS_URI`：Milvus 连接地址
- `MILVUS_TOKEN`：如使用鉴权则传入
- `MILVUS_VECTOR_DIM`：必须与 embedding 维度一致
- `MILVUS_COLLECTION_NAME`：Milvus collection 名称

---

## 5.3 Milvus collection schema 设计

建议 schema：

- `id`: VARCHAR，主键，使用 `chunk_id`
- `embedding`: FLOAT_VECTOR，维度 `MILVUS_VECTOR_DIM`
- `content`: VARCHAR / TEXT
- `source`: VARCHAR
- `title`: VARCHAR
- `doc_id`: VARCHAR
- `chunk_index`: INT64
- `metadata_json`: JSON 字符串

### 原因

- `chunk_id` 与现有系统天然匹配
- `metadata_json` 保留灵活扩展性
- 常用过滤字段单独拆列，便于未来做精确过滤

---

## 5.4 Milvus 写入逻辑

文档写入流程：

1. `DocumentProcessor` 生成 chunks
2. `EmbeddingService` 生成 embeddings
3. `MilvusVectorStore.add_documents()` 组装实体
4. 自动创建 collection（若不存在）
5. 执行 upsert / insert

### 写入策略

- 使用 `chunk_id` 作为唯一主键
- 如果同 ID 重复写入，优先执行 upsert 语义
- metadata 统一序列化为 JSON 字符串存储

---

## 5.5 Milvus 检索逻辑

向量检索流程：

1. 对 query 生成 embedding
2. 调用 Milvus `search`
3. 返回 top_k 候选
4. 映射为统一结果结构：
   - `content`
   - `metadata`
   - `distance`
   - `id`

### 来源过滤

当前阶段对 `source` 过滤采用 Milvus scalar filter：

- `source in ["小红书", "全网"]`

若过滤结构与当前调用格式不完全一致，则在 `MilvusVectorStore` 内做适配转换。

---

## 6. BM25 与 Hybrid Retrieval 设计

当前 BM25 模块保持不变：

- 读取 `processed` 文档
- 轻量 token 化
- 计算 BM25 分数

Hybrid Retrieval 流程保持：

1. Vector Retrieval（Milvus / Chroma）
2. Keyword Retrieval（BM25）
3. 分数归一化
4. 结果去重
5. 融合排序

默认权重：

- `vector_weight = 0.65`
- `keyword_weight = 0.35`

---

## 7. 对现有模块的改动点

### 改动点 1：`backend/config.py`
新增 Milvus 配置项与向量后端切换配置。

### 改动点 2：`backend/rag/vector_store.py`
从单一 `Chroma` 实现升级为：

- `BaseVectorStore` 接口风格
- `ChromaVectorStore`
- `MilvusVectorStore`
- `get_vector_store()` 工厂逻辑

### 改动点 3：`backend/rag/retriever.py`
原则上不改接口，仅继续依赖 `get_vector_store()` 返回统一对象。

### 改动点 4：`pyproject.toml`
新增 `pymilvus` 依赖声明。

---

## 8. 接口兼容性说明

本方案要求：

- 现有 REST API `/rag/search` 不改请求结构
- 现有 `SearchAgent` 不改调用方式
- 现有 `RAGTool` 不改调用方式
- 现有前端完全无需改动

也就是说，本次升级应做到：

- **内部增强**
- **外部无感**

---

## 9. 风险与规避

### 风险 1：Milvus 本地服务未启动
规避：
- 保留 `Chroma` 回退能力
- 启动失败时日志给出明确提示

### 风险 2：Embedding 维度与 Milvus schema 不一致
规避：
- 配置中显式声明 `MILVUS_VECTOR_DIM`
- collection 初始化时严格按配置建表

### 风险 3：Metadata 过滤兼容性问题
规避：
- 当前只对 `source` 做明确结构化支持
- 其余 metadata 先存 JSON，后续再增强

### 风险 4：pymilvus 版本兼容问题
规避：
- 只使用基础连接、建 collection、插入、搜索能力
- 避免在本阶段引入复杂高级特性

---

## 10. 本次实际实施范围

本次代码改造将覆盖：

- 增加 Milvus 配置
- 新增 Milvus 向量存储实现
- 将向量后端改为可切换
- 保留当前 BM25 与 Hybrid Retrieval 逻辑
- 保证当前 API 与 Agent 主链路继续正常运行

本次**不实施**以下内容：

- Query Rewrite
- Rerank 模型
- 预算 / 天数 / 城市结构化过滤
- 多级缓存系统
- Milvus 分区优化与分片调优

---

## 11. 结论

基于当前项目代码结构，最合理的接入路径不是粗暴替换所有向量逻辑，而是：

1. 先保留当前 BM25 与 Hybrid Retrieval 主流程
2. 把向量存储层升级为 `Milvus / Chroma` 可切换
3. 默认按配置支持 Milvus 接入
4. 保证项目主流程稳定、功能可运行

该方案改动集中、风险可控、与当前需求文档目标一致，适合作为当前版本的 Milvus 落地方案。
