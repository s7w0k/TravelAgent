# Travel Agent 架构说明（基于当前代码实现）

## 一、项目概述

Travel Agent 当前是一个前后端分离的旅行问答与行程生成系统：

- 后端以 FastAPI 提供 WebSocket 与 REST 接口；
- 核心编排采用 LangGraph，串联 Search / Planner / Writer / Visualization 四类 Agent；
- 同时接入 RAG（Chroma 本地向量库 + 关键词检索）与会话记忆模块；
- 前端通过 React + WebSocket 展示流式执行过程和最终攻略。

系统目标是将“用户自然语言需求”转换为“带上下文约束的旅行攻略内容”，并可选输出路线图信息。

---

## 二、技术栈

| 层级 | 当前实现技术 |
|------|--------------|
| 后端服务 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph（StateGraph） |
| LLM | DeepSeek Chat（`langchain-deepseek`） |
| 工具集成 | MCP（`langchain-mcp-adapters` + `mcp`） |
| 检索增强 | Chroma 持久化向量库 + 本地关键词检索 + 混合重排 |
| Embedding | DashScope Embeddings（`langchain_community`） |
| 前端 | React 18 + TypeScript + Vite + Tailwind |
| 状态管理 | Zustand |
| 配置管理 | Pydantic + python-dotenv |

---

## 三、项目结构

```text
TravelAgent/
├── backend/
│   ├── main.py                       # FastAPI 入口、WebSocket、路由注册
│   ├── config.py                     # 全局配置与环境变量
│   ├── agent_manager.py              # MultiAgentGraph 单例管理
│   ├── session_memory.py             # 会话持久化/长期记忆/摘要与压缩
│   ├── memory_api_routes.py          # Memory 查询接口
│   ├── agents/
│   │   ├── coordinator.py            # LangGraph 状态流与事件流
│   │   ├── search_agent.py           # 搜索 + 知识补充
│   │   ├── planner_agent.py          # 行程结构化规划
│   │   ├── writer_agent.py           # 攻略文本生成
│   │   ├── visualization_agent.py    # 路线图描述/图片生成
│   │   └── api_routes.py             # 多 Agent REST 接口
│   └── rag/
│       ├── api_routes.py             # RAG 管理与检索接口
│       ├── retriever.py              # 混合检索与重排核心
│       ├── vector_store.py           # Chroma 读写与查询
│       ├── embedding_service.py      # Embedding 服务封装
│       ├── keyword_retriever.py      # 关键词检索
│       ├── document_processor.py     # 文档切分与元数据处理
│       └── rag_tool.py               # 给 Agent 使用的 RAG 工具层
│
├── src/
│   ├── agent.py                      # 早期/兼容 Agent 入口逻辑
│   ├── mcp_tools.py                  # MCP 工具发现与连接
│   ├── prompts.py                    # 系统提示词
│   ├── schemas.py                    # 共享数据模型
│   └── skill_loader.py               # 技能文本加载
│
├── frontend/
│   ├── src/components/               # ChatBox、DetailPanel 等 UI
│   ├── src/hooks/useWebSocket.ts     # WebSocket 数据流处理
│   ├── src/stores/chatStore.ts       # 前端状态管理
│   └── package.json                  # 前端依赖与脚本
│
├── skills/                           # 旅行技能模板与工具参考
├── data/                             # 向量库、知识库、会话记忆持久化
├── scripts/                          # 初始化知识库等脚本
└── docs/                             # 架构与方案文档
```

---

## 四、Multi-Agent 架构

### 4.1 Agent 组件职责

| Agent | 主要职责 | 关键输入 | 关键输出 |
|------|----------|---------|---------|
| SearchAgent | 外部信息补充 + RAG 上下文获取 | 用户问题 | `knowledge_context` |
| PlannerAgent | 生成结构化 TravelPlan、预算可行性判断 | 用户需求 + 检索上下文 | `travel_plan` |
| WriterAgent | 产出最终攻略文本（模板化风格输出） | 原始需求 + travel_plan + context | `guide_content` |
| VisualizationAgent | 根据行程生成路线描述，配置可用时生成图片 | travel_plan + guide_content | `route_map` |

### 4.2 LangGraph 节点流

```text
user_request
   │
   ▼
search_node
   ▼
planner_node
   ▼
writer_node
   ▼
visualize_node
   ▼
END
```

当前图在 `build_graph()` 中固定按顺序连接，`enable_visualization=False` 时可在节点内返回空结果。

### 4.3 状态模型（AgentState）

核心状态字段包括：

- 输入域：`user_request`、`enable_search`、`enable_visualization`、`style`；
- 中间域：`search_context`、`travel_plan`、`guide_content`、`route_map`；
- 追踪域：`current_node`、`error`。

同时在流式执行中会转换 LangGraph 事件为前端可消费事件（`start`、`step_start`、`step_end`、`llm_start`、`llm_end`、`complete`、`error`）。

---

## 五、MCP 集成

### 5.1 工具初始化

`src/mcp_tools.py` 通过 `MultiServerMCPClient` 连接 MCP 服务端并发现工具，默认配置：

- `12306`：`npx -y 12306-mcp`（铁路票务相关）；
- `amap`：`npx -y @amap/amap-maps-mcp-server`（地图相关，读取 `AMAP_MAPS_API_KEY`）。

### 5.2 使用方式

- `AgentManager.initialize()` 启动时初始化 MCP 工具；
- 初始化失败时系统降级为“无工具模式”，不会阻断主流程；
- 成功获取的工具列表注入 PlannerAgent（以及协同图实例）。

### 5.3 技能模板协同

`skills/travel_plan.md` 作为输出格式与工具意图约束来源，WriterAgent 会按固定旅行计划结构组织最终内容。

---

## 六、RAG 模块

### 6.1 检索链路

```text
文档输入 -> DocumentProcessor 切块 -> EmbeddingService 向量化
        -> VectorStore(Chroma) 持久化

查询输入 -> Query 重写/约束抽取
        -> 向量检索 + 关键词检索
        -> 混合打分 + 约束过滤 + 重排
        -> TopK 返回
```

### 6.2 当前增强能力

`backend/rag/retriever.py` 已实现：

- 别名归一化（如城市别称）；
- Query Rewrite（可开关）；
- 混合检索（向量 + 关键词，带权重）；
- 约束感知过滤（城市、预算、天数、人群、季节）；
- 重排序与信号记录（输出到 metadata）。

### 6.3 存储与健康性

- 向量后端当前实际使用 Chroma PersistentClient；
- 持久化目录由 `CHROMA_PERSIST_DIR` 控制；
- 提供 `GET /rag/vector/health` 用于检查集合可用性与文档规模。

---

## 七、配置管理

### 7.1 配置来源

- `backend/config.py` 在启动时加载项目根目录 `.env`；
- 配置统一收敛到 `Settings`（Pydantic BaseModel）；
- 业务模块通过 `get_settings()` 读取运行参数。

### 7.2 关键配置分组

- 服务参数：`HOST`、`PORT`、`DEBUG`、`LOG_LEVEL`；
- 模型密钥：`DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`、`SEEDREAM_API_KEY`、`AMAP_MAPS_API_KEY`；
- 记忆参数：`ENABLE_SESSION_PERSISTENCE`、`ENABLE_LONG_TERM_MEMORY`、`ENABLE_DYNAMIC_SUMMARY`、`ENABLE_CONTEXT_COMPRESSION`；
- RAG 参数：`RAG_TOP_K`、`RAG_ENABLE_HYBRID`、`RAG_ENABLE_RERANK`、`RAG_VECTOR_WEIGHT`、`RAG_KEYWORD_WEIGHT` 等；
- 存储路径：`SESSION_MEMORY_DIR`、`CHROMA_PERSIST_DIR`、`KNOWLEDGE_BASE_DIR`。

---

## 八、API 接口

### 8.1 WebSocket

- `WS /ws`

消息处理支持纯文本或 JSON（含 `message`、`session_id`、`user_id`），服务端会回传执行阶段事件与最终结果。

常见事件类型（当前代码）：

- `received`
- `rag_context`
- `memory_context`
- `history_summary`
- `start`
- `step_start`
- `step_end`
- `llm_start`
- `llm_end`
- `complete`
- `final`
- `error`

### 8.2 REST

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根健康检查 |
| GET | `/api/health` | Agent 就绪状态 |
| POST | `/api/multi-agent/chat` | 非流式多 Agent 对话 |
| GET | `/api/multi-agent/status` | 多 Agent 组件状态 |
| POST | `/rag/documents` | 添加知识文档 |
| POST | `/rag/search` | 混合检索 |
| POST | `/rag/search/xiaohongshu` | 来源限定检索 |
| GET | `/rag/stats` | 知识库统计 |
| GET | `/rag/vector/health` | 向量后端健康检查 |
| GET | `/memory/sessions/{session_id}` | 会话详情 |
| GET | `/memory/users/{user_id}/sessions` | 用户会话列表 |
| GET | `/memory/users/{user_id}/memory` | 用户长期记忆 |

---

## 九、依赖项（以当前项目元数据为准）

从 `src/travel_agent.egg-info/requires.txt` 可见核心依赖：

- Agent / LLM：`langchain`、`langchain-core`、`langgraph`、`langchain-deepseek`；
- MCP：`langchain-mcp-adapters`、`mcp`；
- RAG：`chromadb`、`pypdf`、`python-docx`；
- 服务：`fastapi`、`uvicorn[standard]`、`websockets`；
- 基础：`pydantic`、`python-dotenv`、`sqlalchemy`、`pyyaml`。

前端依赖见 `frontend/package.json`，核心为 React 18、TypeScript 5、Vite 5、Zustand、Tailwind。

---

## 十、总结

当前 Travel Agent 的落地形态可以概括为：

1. **编排层**：LangGraph 驱动的四段式 Agent 工作流；
2. **增强层**：混合 RAG 与会话记忆共同提升回答上下文质量；
3. **能力层**：MCP 工具可插拔，失败可降级，保证主流程可用；
4. **交互层**：WebSocket 实时事件流 + REST 管理接口并行提供。

该架构已经具备“可持续演进”的基础：模块边界清晰、配置集中、数据持久化路径明确，适合继续扩展真实搜索接入、检索评估、图像生成与业务监控能力。
