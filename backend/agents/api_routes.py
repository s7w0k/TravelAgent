"""
多 Agent 系统 API 路由
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量 - 从项目根目录
root_dir = Path(__file__).parent.parent.parent
env_file = root_dir / ".env"
print(f"加载环境变量 from: {env_file}, exists: {env_file.exists()}")
if env_file.exists():
    load_dotenv(env_file, override=True)

# 验证环境变量
print(f"DEEPSEEK_API_KEY loaded: {bool(os.getenv('DEEPSEEK_API_KEY'))}")

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-agent", tags=["多Agent"])


class MultiAgentRequest(BaseModel):
    """多 Agent 请求"""
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    enable_search: bool = True
    enable_visualization: bool = True
    style: str = "friendly"  # friendly / professional / fun


class MultiAgentResponse(BaseModel):
    """多 Agent 响应"""
    guide_content: str
    route_map: Optional[dict] = None
    travel_plan: Optional[dict] = None
    search_context: str = ""
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/chat", response_model=MultiAgentResponse)
async def multi_agent_chat(request: MultiAgentRequest):
    """多 Agent 聊天接口

    处理流程：
    1. Search Agent: 搜索 + RAG 检索
    2. Planner Agent: 生成旅行计划
    3. Writer Agent: 生成攻略文本
    4. Visualization Agent: 生成路线图（可选）
    """
    try:
        from backend.agents.coordinator import get_coordinator
        from backend.main import build_input_messages, retrieve_context
        from backend.schemas import ConversationMessage
        from backend.session_memory import get_session_memory_store

        store = get_session_memory_store()
        session_id = request.session_id or store.create_session_id()
        user_id = request.user_id or f"session_user::{session_id}"
        conversation_history = store.load_messages(session_id)
        memory_context = store.build_memory_context(user_id)
        session_context = store.build_session_context(session_id, conversation_history)
        context = await retrieve_context(request.message)

        input_messages = build_input_messages(
            user_input=request.message,
            recent_messages=session_context.get("recent_messages", conversation_history),
            context=context,
            memory_context=memory_context,
            history_summary=session_context.get("summary", ""),
            structured_context=session_context.get("structured_text", ""),
        )

        system_parts = []
        history_parts = []
        for msg in input_messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                history_parts.append(f"[{role}] {content}")

        composed_sections = []
        if system_parts:
            composed_sections.append("## 系统与上下文\n" + "\n\n".join(system_parts))
        if history_parts:
            composed_sections.append("## 最近对话历史\n" + "\n".join(history_parts[:-1]))
        composed_sections.append(f"## 当前用户问题\n{request.message}")
        enhanced_request = "\n\n".join(section for section in composed_sections if section.strip())

        coordinator = get_coordinator()
        result = await coordinator.process(
            user_request=enhanced_request,
            enable_search=request.enable_search,
            enable_visualization=request.enable_visualization,
            style=request.style,
        )

        conversation_history.append(ConversationMessage(role="user", content=request.message))
        conversation_history.append(ConversationMessage(role="assistant", content=result.guide_content))
        store.save_session(session_id, user_id, conversation_history)
        store.update_user_memory_from_text(user_id, request.message)

        return MultiAgentResponse(
            guide_content=result.guide_content,
            route_map=result.route_map,
            travel_plan=result.travel_plan,
            search_context=result.search_context,
            session_id=session_id,
            user_id=user_id,
        )

    except Exception as e:
        logger.error(f"多 Agent 处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def agent_status():
    """检查 Agent 状态"""
    try:
        from backend.agents.coordinator import get_coordinator
        coordinator = get_coordinator()

        graph = coordinator._graph

        return {
            "status": "ready",
            "agents": {
                "search": graph.search_agent is not None,
                "planner": graph.planner_agent is not None,
                "writer": graph.writer_agent is not None,
                "visualization": graph.visualization_agent is not None,
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
