# Milvus Lite 运行与验证说明

## 1. 目标

本文档用于帮助你将当前项目中的 `Milvus Lite + BM25 + Hybrid Retrieval` 真正跑通，并完成基础验证。

当前项目已经具备：

- Milvus Lite 向量存储后端接入
- BM25 关键词检索
- Hybrid Retrieval 融合
- 向量后端健康检查接口
- 本地验证脚本

---

## 2. 关键配置

请在项目根目录的 `.env` 中至少补充以下配置：

```env
RAG_VECTOR_BACKEND=milvus
MILVUS_LITE_PATH=./data/milvus_lite.db
MILVUS_COLLECTION_NAME=travel_knowledge
MILVUS_VECTOR_DIM=1536
MILVUS_METRIC_TYPE=COSINE
```

说明：

- `MILVUS_LITE_PATH` 是本地 Lite 数据文件路径
- `MILVUS_VECTOR_DIM` 必须与 embedding 模型维度一致
- 当前代码默认 embedding 失败时会回退到 1536 维零向量，因此默认值写为 1536

---

## 3. 安装依赖

执行：

```bash
uv pip install -e .
uv pip install -e ".[backend]"
```

如果你只想补齐向量检索相关依赖，也可以执行：

```bash
uv pip install pymilvus milvus-lite langchain-community
```

---

## 4. 启动 Milvus Lite

Milvus Lite 不需要单独启动服务。

只要依赖安装完成，且 `.env` 中指定了：

```env
MILVUS_LITE_PATH=./data/milvus_lite.db
```

程序会在第一次访问时自动创建本地 Lite 数据文件与 collection。

---

## 5. 后端健康检查接口

当前已增加接口：

```text
GET /rag/vector/health
```

启动后端后访问该接口，正常时返回类似：

```json
{
  "backend": "milvus_lite",
  "healthy": true,
  "collection_name": "travel_knowledge",
  "document_count": 0,
  "detail": "Milvus Lite ok: data/milvus_lite.db"
}
```

如果返回 `healthy: false`，说明 Lite 初始化失败。

---

## 6. 本地验证脚本

当前已提供脚本：

`scripts/verify_milvus.py`

执行：

```bash
python scripts/verify_milvus.py
```

脚本会自动完成：

1. 向量后端健康检查
2. 插入两条测试文档
3. 执行一次混合检索
4. 打印检索结果

如果脚本成功执行，说明：

- Milvus Lite 已初始化
- Collection 可自动创建
- 文档可写入
- 向量检索链路可跑通
- Hybrid Retrieval 主链路可运行

---

## 7. 接口验证步骤

### 7.1 添加测试文档

调用：

```text
POST /rag/documents
```

请求体示例：

```json
{
  "title": "苏州两日游攻略",
  "content": "苏州适合 2 天游玩，可安排拙政园、平江路、山塘街和苏州博物馆。",
  "source": "全网",
  "metadata": {
    "city": "苏州",
    "theme": "园林"
  }
}
```

### 7.2 执行检索

调用：

```text
POST /rag/search
```

请求体示例：

```json
{
  "query": "苏州园林两日游",
  "top_k": 3
}
```

### 7.3 查看统计信息

调用：

```text
GET /rag/stats
```

---

## 8. 常见问题

### 问题 1：健康检查失败

排查顺序：

1. 确认 `milvus-lite` 已安装
2. 确认 `MILVUS_LITE_PATH` 路径可写
3. 确认本地目录存在读写权限

### 问题 2：插入时报维度不一致

原因：
- `MILVUS_VECTOR_DIM` 与 embedding 实际维度不一致

处理：
- 把 `.env` 中的 `MILVUS_VECTOR_DIM` 改成真实 embedding 维度
- 必要时删除原 Lite 数据文件后重新初始化

### 问题 3：检索无结果

排查顺序：

1. 确认测试文档已成功写入
2. 查看 `/rag/stats` 中的文档数是否增长
3. 检查 embedding 是否正常返回
4. 检查 query 是否与测试文档语义相关

---

## 9. 推荐验证顺序

建议按以下顺序操作：

1. 配置 `.env`
2. 安装依赖
3. 启动后端
4. 调用 `/rag/vector/health`
5. 运行 `python scripts/verify_milvus.py`
6. 再通过 `/rag/documents` + `/rag/search` 验证接口

---

## 10. 当前状态说明

截至当前版本，项目已经具备：

- `Milvus Lite` 向量检索
- `BM25` 关键词检索
- `Hybrid Retrieval` 融合
- 健康检查接口
- 基础验证脚本

尚未继续扩展的部分包括：

- Query Rewrite
- Rerank
- 结构化条件过滤（预算 / 天数 / 城市）
- 更复杂的 Lite 数据维护策略

这些内容建议作为下一阶段迭代。
