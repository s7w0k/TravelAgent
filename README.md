# Travel Agent - 智能旅行规划助手

<div align="center">

基于 LangGraph 和 LLM 的智能旅行规划系统

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://reactjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 项目简介

Travel Agent 是一个基于大语言模型的智能旅行规划助手，通过自然语言对话为用户提供个性化的旅行规划服务。系统采用前后端分离架构，后端基于 LangGraph 构建 Agent 工作流，集成多个 MCP（Model Context Protocol）工具，前端实现实时对话界面和执行过程可视化。

### 核心能力

- 🤖 **智能对话**：基于 LLM 的自然语言理解，支持多轮对话和上下文记忆
- 🚄 **火车票查询**：实时查询 12306 火车票余票信息（高铁/动车/普速列车）
- 🗺️ **地图导航**：高德地图服务，支持路线规划、周边搜索、天气查询
- 📊 **实时监控**：实时显示 Agent 执行过程、Token 消耗统计、工具调用详情
- 🔍 **可视化**：执行时间瀑布图、事件流分析、性能统计

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (React + TypeScript)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  ChatBox    │  │ StepDisplay │  │   TimelinePanel     │  │
│  │  聊天界面    │  │  步骤显示    │  │   详情面板/瀑布图    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕ WebSocket
┌─────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI + Python)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ WebSocket    │  │ Agent        │  │  Event Converter │  │
│  │  Endpoint    │  │ Manager      │  │  + Monitor       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                     服务层 (Services)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ LangGraph    │  │ MCP Tools    │  │  LLM (DeepSeek)  │  │
│  │ Agent        │  │ Manager      │  │                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- uv (Python 包管理器)
- npm 或 yarn

### 1. 克隆项目

```bash
git clone <repository-url>
cd Travel_Agent
```

### 2. 安装依赖

```bash
# 安装 Python 依赖（含后端）
uv pip install -e ".[backend]"

# 安装前端依赖
cd frontend && npm install
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# DeepSeek API 密钥（必需）
DEEPSEEK_API_KEY=sk-your-api-key-here

# 高德地图 API 密钥（地图服务必需）
AMAP_MAPS_API_KEY=your-amap-key-here

# 可选配置
LOG_LEVEL=INFO
RECURSION_LIMIT=25
MAX_CONVERSATION_HISTORY=20
```

### 4. 启动服务

**方式一：使用启动脚本（推荐）**

```bash
# 启动后端
python start_server.py

# 另开终端启动前端
cd frontend && npm run dev
```

**方式二：分别启动**

```bash
# 终端 1 - 启动后端
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2 - 启动前端
cd frontend && npm run dev
```

访问 http://localhost:3000 使用 Web 界面。

---

## 💡 使用示例

### 基础对话

```
用户：你好，请介绍一下你自己

AI: 你好！我是 TravelBot，一位专业的旅行规划助手...
```

### 旅行规划

```
用户：帮我规划一个从北京到上海的 3 天旅行

AI: 好的，我来帮您规划北京到上海的 3 天旅行。
    让我先查询一下火车票信息...
    [调用 12306 工具查询车次]
    [调用高德地图规划路线]
    [查询天气信息]
    
    以下是为您定制的旅行计划：
    
    ## 📋 旅行计划
    
    ### 🚄 交通信息
    - 车次：G103
    - 出发时间：08:00 北京南
    - 到达时间：12:30 上海虹桥
    - 二等座：¥662
    
    ### 🗺️ 行程安排
    Day 1: 抵达上海，游览外滩、南京路
    Day 2: 迪士尼乐园
    Day 3: 豫园、城隍庙，返程
    
    ### 💰 预算估算
    - 交通：¥1500
    - 住宿：¥800
    - 餐饮：¥500
    - 门票：¥600
    - 总计：¥3400
```

### 多轮对话

```
用户：我想从北京去上海
AI: 好的，请问您的出行日期是？

用户：下周五
AI: 好的，正在查询下周五北京到上海的高铁...
    [自动理解"下周五"的日期]
    共有 15 个车次，推荐 G103 次...

用户：二等座多少钱？
AI: G103 的二等座价格是 662 元
    [理解"二等座"指的是之前查询的车次]
```

---

## 📁 项目结构

```
Travel_Agent/
├── backend/                    # FastAPI 后端服务
│   ├── __init__.py            # 日志配置
│   ├── agent_manager.py       # Agent 管理器（单例模式）
│   ├── config.py              # 配置管理（Pydantic）
│   ├── logger.py              # 日志配置模块
│   ├── main.py                # FastAPI 应用入口
│   ├── monitor_handler.py     # 监控事件处理器
│   └── schemas.py             # 类型定义
│
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── components/        # React 组件
│   │   │   ├── ChatBox.tsx    # 聊天界面
│   │   │   ├── DetailPanel.tsx # 详情面板
│   │   │   └── StepDisplay.tsx # 步骤显示
│   │   ├── hooks/             # React Hooks
│   │   │   └── useWebSocket.ts # WebSocket 连接
│   │   ├── stores/            # 状态管理（Zustand）
│   │   │   └── chatStore.ts   # 聊天状态
│   │   └── types/             # TypeScript 类型
│   ├── package.json
│   └── vite.config.ts
│
├── src/                        # Agent 核心代码
│   ├── __init__.py            # 日志配置
│   ├── agent.py               # TravelAgent 定义
│   ├── mcp_tools.py           # MCP 工具管理
│   ├── monitor.py             # 实时监控器
│   ├── prompts.py             # System Prompt 管理
│   ├── schemas.py             # 类型定义
│   └── skill_loader.py        # 技能配置加载器
│
├── logs/                       # 日志文件
│   ├── backend_YYYY-MM-DD.log # 后端日志
│   └── YYYY-MM-DD.log         # Agent 日志
│
├── .env                        # 环境变量配置
├── .gitignore                 # Git 忽略规则
├── pyproject.toml             # Python 项目配置
├── start_server.py            # 启动脚本
├── README.md                  # 本文档
└── test_websocket.py          # WebSocket 测试脚本
```

---

## 🔧 技术栈

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.100+ | Web 框架 |
| LangGraph | Latest | Agent 工作流编排 |
| LangChain | Latest | LLM 应用开发框架 |
| DeepSeek | API | 大语言模型 |
| MCP | Latest | 工具集成协议 |
| Pydantic | Latest | 数据验证 |
| uvicorn | Latest | ASGI 服务器 |

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5 | 类型系统 |
| Vite | 5 | 构建工具 |
| Tailwind CSS | 3 | 样式框架 |
| Zustand | 4 | 状态管理 |
| react-markdown | 9 | Markdown 渲染 |
| Lucide React | Latest | 图标库 |

---

## 📊 功能特性

### 1. 实时监控

系统实时展示 Agent 的执行过程，包括：

- **步骤显示**：当前执行的节点（LLM 思考、工具调用等）
- **Loading 动画**：视觉反馈当前状态
- **Token 统计**：输入/输出/总计，实时更新
- **步骤替换**：新步骤自动替换上一个，保持界面简洁

### 2. 详情面板

点击详情按钮可查看完整执行时间流：

- **瀑布图**：可视化展示各步骤耗时
- **事件列表**：每个调用的详细信息
- **统计卡片**：LLM 调用次数、工具调用次数、Token 消耗
- **时间戳**：精确到毫秒的事件时间

### 3. 对话管理

- **上下文记忆**：自动记住之前的对话内容
- **历史限制**：保留最近 20 条，避免 Token 超限
- **独立会话**：每个 WebSocket 连接独立的历史

### 4. 工具集成

通过 MCP 协议集成多个工具：

- **12306 火车票**：实时查询余票、车次信息
- **高德地图**：路线规划、周边搜索、天气查询
- **可扩展**：支持添加新的 MCP 工具

---

## ⚙️ 配置说明

### 环境变量

| 变量名 | 必需 | 说明 | 示例 |
|--------|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 | `sk-xxx` |
| `AMAP_MAPS_API_KEY` | ✅ | 高德地图 API 密钥 | `xxx` |
| `LOG_LEVEL` | ❌ | 日志级别 | `INFO`/`DEBUG` |
| `RECURSION_LIMIT` | ❌ | Agent 递归限制 | `25` |
| `MAX_CONVERSATION_HISTORY` | ❌ | 最大对话历史数 | `20` |

### 高级配置

在 `backend/config.py` 中可调整以下参数：

```python
# Agent 配置
RECURSION_LIMIT: int = 25  # 最大递归次数
MAX_CONVERSATION_HISTORY: int = 20  # 对话历史限制

# 服务器配置
HOST: str = "0.0.0.0"
PORT: int = 8000

# Token 限制
MAX_INPUT_LENGTH: int = 200  # 工具输入截断长度
MAX_OUTPUT_LENGTH: int = 300  # 工具输出截断长度
```

---

## 🧪 测试

### WebSocket 测试

使用提供的测试脚本：

```bash
uv run python test_websocket.py
```

### 健康检查

```bash
# 基础健康检查
curl http://localhost:8000

# Agent 状态检查
curl http://localhost:8000/api/health
```

### 日志查看

```bash
# 实时查看后端日志
tail -f logs/backend_$(date +%Y-%m-%d).log

# 查看错误日志
grep "ERROR" logs/backend_*.log | tail -20
```

---
