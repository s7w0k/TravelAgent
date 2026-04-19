# 召回优化链路实施方案

## 1. 目标说明

本方案对应 `需求文档 2：Query Rewrite / 去重 / Rerank / 条件过滤召回链路`，基于当前项目已有的 RAG 能力，给出一套**最小改动、可运行、与现有接口兼容**的落地方案。

当前现状：

- 已有 `Retriever` 统一检索入口
- 已有 `Milvus Lite` 向量检索
- 已有本地 `BM25` 关键词检索
- 已有 Hybrid Retrieval 融合逻辑
- 但尚未形成标准化的召回增强流水线

因此，本次实现目标是：

1. 在不改动上层 Agent / API 调用方式的前提下
2. 仅增强 `backend/rag/retriever.py` 主链路及少量配置
3. 实现 Query Rewrite、候选去重、轻量 Rerank、条件过滤四个能力
4. 保证整体功能可行且正常运行

---

## 2. 当前代码结构与切入点

### 2.1 主入口：`backend/rag/retriever.py`
当前已负责：

- query 进入检索主链路
- 调用向量检索
- 调用 BM25 检索
- 执行基础融合与排序

该文件最适合作为本次增强的唯一核心落点。

### 2.2 关键词检索：`backend/rag/keyword_retriever.py`
当前已提供：

- 基于 processed 文档的 BM25 召回
- 按 source 做简单过滤

该模块本次尽量不改，避免影响索引构建稳定性。

### 2.3 文档处理：`backend/rag/document_processor.py`
当前 chunk metadata 已包含：

- `title`
- `source`
- `doc_id`
- `chunk_index`
- 用户新增的自定义 metadata

这意味着：

- 预算 / 天数 / 城市 / 人群 / 季节等条件，只要历史入库时 metadata 有携带，就可直接用于后处理过滤与重排
- 即使 metadata 不完整，也不影响主流程运行

---

## 3. 实现原则

### 原则 1：不改外部接口
以下接口保持不变：

- `Retriever.retrieve()`
- `RAGTool.search()`
- `/rag/search`
- 上层 Agent 调用方式

### 原则 2：先做规则增强，不引入额外模型依赖
当前版本不接入额外 reranker 模型，避免：

- 依赖膨胀
- 推理延迟显著增加
- 本地环境复杂化

因此本次采用：

- 规则式 Query Rewrite
- 规则式条件解析
- 规则式轻量 Rerank

### 原则 3：过滤与降权并存
为了避免 metadata 不全导致结果被误删：

- 强不匹配时剔除
- 弱不匹配时降权
- metadata 缺失时尽量保留候选

---

## 4. 流水线设计

目标流水线：

```text
用户 Query
  -> Query 解析
  -> Query Rewrite
  -> 多路召回（vector + BM25）
  -> 候选聚合
  -> 去重
  -> 条件过滤
  -> 轻量 Rerank
  -> TopK 输出
```

---

## 5. Query Rewrite 设计

### 5.1 目标
解决当前 query 直接检索导致的：

- 口语化表达不稳定
- 城市别名无法命中
- 人群玩法词不统一
- 查询过短导致召回面窄

### 5.2 规则式改写策略
在 `Retriever` 内增加静态词典：

#### 城市别名
- `魔都 -> 上海`
- `帝都 -> 北京`
- `姑苏 -> 苏州`
- `鹏城 -> 深圳`
- `羊城 -> 广州`

#### 玩法 / 人群表达
- `遛娃 -> 亲子`
- `带娃 -> 亲子`
- `学生党 -> 学生`
- `约会 -> 情侣`
- `打卡 -> 攻略`

### 5.3 生成查询集合
对每个 query 生成：

1. 原始 query
2. 别名归一化 query
3. 玩法扩展 query
4. 若抽取到城市，则追加 `城市 + 原需求` 的加强版 query

### 5.4 范围控制
避免 rewrite 过多导致性能问题：

- 最多生成 3 到 4 条子查询
- 去重后执行召回

---

## 6. Query 解析与条件抽取设计

### 6.1 抽取目标
从 query 中尽量识别：

- `destination/city`
- `days`
- `budget`
- `persona`
- `season/month`

### 6.2 规则实现方式
采用正则 + 词典识别：

#### 城市
从城市别名字典和标准城市词典中识别

#### 天数
识别如：
- `2天`
- `三日游`
- `玩 4 天`

统一归一到整数 `days`

#### 预算
识别如：
- `预算 2000`
- `3000 元以内`
- `人均 1500`

统一归一到预算上限 `budget_max`

#### 人群
识别：
- `亲子`
- `情侣`
- `学生`
- `老人/长者`

#### 季节 / 月份
识别：
- `春季`
- `暑假`
- `十一`
- `10月`

---

## 7. 去重设计

### 7.1 当前问题
现有融合逻辑虽然有基础主键合并，但仍可能出现：

- 同文档多 chunk 重复占位
- 标题极度相近的重复结果
- 相同内容前缀的重复候选

### 7.2 去重策略
按以下优先级处理：

1. `chunk_id` 去重
2. `doc_id + chunk_index` 去重
3. 标题标准化后近似去重
4. 内容前 80~120 字标准化后近似去重

### 7.3 保留规则
若多个候选命中同一主键：

- 保留融合分更高的那个
- 保留 metadata 更完整的那个

---

## 8. 条件过滤设计

### 8.1 目标
对有明确约束的 query，在召回后做条件约束处理，提高候选可用性。

### 8.2 过滤字段
支持以下字段：

- 城市：`city` / `destination`
- 天数：`days`
- 预算：`budget` / `budget_max`
- 人群：`persona`
- 季节：`season` / `month`

### 8.3 过滤规则
#### 城市
- 若 query 中识别到城市，且候选 metadata 明确标记其他城市，则剔除
- 若 metadata 无城市字段，则保留

#### 天数
- 若候选天数明显大于 query 天数很多，则降权
- 若基本接近，则加分
- 若无字段，则不处罚

#### 预算
- 若候选预算明显超过用户预算上限，则降权
- 若预算在范围内，则加分
- 若无字段，则不处罚

#### 人群 / 季节
- 命中则加分
- 明确冲突则小幅降权
- 无字段则不处罚

---

## 9. Rerank 设计

### 9.1 目标
在不引入额外模型的前提下，让最终首屏结果更稳定。

### 9.2 最终得分组成
在已有 `hybrid_score` 基础上，增加规则分：

- `rewrite_hit_score`
- `city_match_score`
- `days_match_score`
- `budget_match_score`
- `persona_match_score`
- `season_match_score`
- `title_hit_score`
- `content_hit_score`

### 9.3 排序逻辑
最终采用：

```text
final_score = hybrid_score + heuristic_bonus - heuristic_penalty
```

并将结果写回 metadata：

- `hybrid_score`
- `final_score`
- `rewrite_query`
- `constraints`
- `rerank_signals`

这样便于后续调试和接口可视化。

---

## 10. 与现有代码的具体改动点

### 改动点 1：`backend/rag/retriever.py`
新增：

- query 解析函数
- rewrite 函数
- 多 query 召回聚合
- 加强去重逻辑
- 条件过滤逻辑
- 轻量 rerank 逻辑

这是本次唯一核心功能改动文件。

### 改动点 2：`backend/config.py`
仅新增少量可调参数，例如：

- 内部候选放大倍数
- rerank 各项权重
- 是否启用 rewrite / rerank / 条件过滤

### 不改动的模块
以下模块本次不改或尽量不改：

- `backend/rag/keyword_retriever.py`
- `backend/rag/vector_store.py`
- `backend/rag/document_processor.py`
- Agent 主链路
- 主 Web/API 框架

---

## 11. 兼容性说明

本方案保证：

- 现有 `/rag/search` 调用参数不变
- 现有 `RAGTool.search()` 参数不变
- 现有前端无需修改
- 现有知识库可继续使用

即使历史 metadata 中没有 `days/budget/persona/season` 字段，系统仍能正常运行，只是相关过滤和重排信号会自动退化为弱规则模式。

---

## 12. 风险与规避

### 风险 1：历史数据 metadata 不完整
规避：
- 缺字段时不强制过滤
- 只做弱降权或直接跳过该规则

### 风险 2：规则写太重导致误伤召回
规避：
- 仅对城市强冲突做硬过滤
- 预算 / 天数优先做软降权

### 风险 3：rewrite 过多导致性能下降
规避：
- 控制子查询数量不超过 4 条
- 内部候选数量只做有限放大

### 风险 4：改动影响现有上层使用
规避：
- 只在 `Retriever` 内部增强
- 对外接口完全保持兼容

---

## 13. 本次实际实施范围

本次将实现：

- Query Rewrite
- Query 结构化约束解析
- 多 query 候选召回聚合
- 候选去重
- 条件过滤
- 轻量规则式 Rerank

本次不实现：

- 基于大模型的 Query Rewrite
- Cross-Encoder / BGE-Reranker 等重排模型
- 向量库侧复杂 metadata 检索 DSL
- 用户长期画像参与重排

---

## 14. 结论

基于当前项目代码结构，最合理的实现方式不是引入新的复杂检索服务，而是：

1. 以 `Retriever` 为单点增强中心
2. 用规则式 Query Rewrite 和条件解析补齐入口能力
3. 在已有 Hybrid Retrieval 上增加去重、过滤和重排
4. 保持上层接口稳定与主流程可运行

该方案改动集中、风险可控、与需求文档目标一致，适合作为当前版本的第二个核心模块落地方案。
