"""
FastAPI 后端服务
提供 WebSocket 接口用于实时 Agent 执行
"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from backend.schemas import ConversationMessage
from backend.session_memory import get_session_memory_store
from agent_manager import AgentManager
from logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动，开始初始化 Agent...")
    agent_manager = AgentManager.get_instance()
    success = await agent_manager.initialize()
    if success:
        logger.info("Agent 初始化成功，服务就绪")
    else:
        logger.error("Agent 初始化失败，服务可能不可用")
    yield
    logger.info("应用关闭，清理资源...")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    app.get("/")(root)
    app.get("/api/health")(health_check)
    app.websocket("/ws")(websocket_endpoint)
    from backend.rag.api_routes import router as rag_router
    from backend.agents.api_routes import router as agent_router
    from backend.memory_api_routes import router as memory_router
    app.include_router(rag_router)
    app.include_router(agent_router)
    app.include_router(memory_router)
    mount_static_files(app)


def mount_static_files(app: FastAPI) -> None:
    backend_dir = Path(__file__).parent
    frontend_dist = backend_dir.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
        logger.info(f"已挂载前端静态文件：{frontend_dist}")


async def root() -> dict:
    logger.info("健康检查请求")
    return {"status": "ok", "message": f"{settings.APP_NAME} is running"}


async def health_check() -> dict:
    agent_manager = AgentManager.get_instance()
    if agent_manager.is_ready():
        return {"status": "healthy", "agent_ready": True, "message": "服务运行正常"}
    return {"status": "initializing", "agent_ready": False, "message": "Agent 正在初始化中"}


async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info(f"WebSocket 连接建立：{websocket.client}")
    conversation_history: list[ConversationMessage] = []
    agent_manager = AgentManager.get_instance()
    store = get_session_memory_store()
    session_id = None
    user_id = None
    try:
        while True:
            session_id, user_id = await handle_client_message(websocket, conversation_history, agent_manager, store, session_id, user_id)
    except WebSocketDisconnect:
        logger.info("客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 错误：{e}", exc_info=True)
        await safe_send_error(websocket, e)


async def handle_client_message(
    websocket: WebSocket,
    conversation_history: list[ConversationMessage],
    agent_manager: AgentManager,
    store,
    current_session_id: str | None,
    current_user_id: str | None,
) -> tuple[str, str | None]:
    raw_message = await websocket.receive_text()
    logger.info(f"收到原始消息：{raw_message[:100]}...")
    user_input = raw_message
    session_id = current_session_id
    user_id = current_user_id
    first_message = len(conversation_history) == 0
    try:
        data = json.loads(raw_message)
        if isinstance(data, dict):
            user_input = data.get("message", raw_message)
            session_id = data.get("session_id", session_id)
            user_id = data.get("user_id", user_id)
    except Exception:
        pass
    if not session_id:
        session_id = store.create_session_id()
    if not user_id and session_id:
        user_id = f"session_user::{session_id}"
    if first_message and settings.ENABLE_SESSION_PERSISTENCE:
        loaded_messages = store.load_messages(session_id)
        if loaded_messages:
            conversation_history.extend(loaded_messages)
    await websocket.send_json({"type": "received", "message": "开始处理...", "session_id": session_id, "user_id": user_id})
    agent = await agent_manager.get_agent()
    context = await retrieve_context(user_input)
    if context:
        logger.info(f"RAG 检索到 {len(context)} 字符的上下文")
        await websocket.send_json({"type": "rag_context", "content": context[:500] + "..." if len(context) > 500 else context})
    memory_context = store.build_memory_context(user_id)
    if memory_context:
        await websocket.send_json({"type": "memory_context", "content": memory_context})
    session_context = store.build_session_context(session_id, conversation_history)
    if session_context.get("summary"):
        await websocket.send_json({"type": "history_summary", "content": session_context["summary"]})
    input_messages = build_input_messages(
        user_input=user_input,
        recent_messages=session_context.get("recent_messages", conversation_history),
        context=context,
        memory_context=memory_context,
        history_summary=session_context.get("summary", ""),
        structured_context=session_context.get("structured_text", ""),
    )
    await execute_and_stream(websocket=websocket, agent=agent, input_messages=input_messages, conversation_history=conversation_history, user_input=user_input)
    if settings.ENABLE_SESSION_PERSISTENCE:
        store.save_session(session_id, user_id, conversation_history)
    store.update_user_memory_from_text(user_id, user_input)
    return session_id, user_id


def build_input_messages(
    user_input: str,
    recent_messages: list[ConversationMessage],
    context: str = "",
    memory_context: str = "",
    history_summary: str = "",
    structured_context: str = "",
) -> list[dict]:
    from skill_loader import SYSTEM_PROMPT
    system_content = SYSTEM_PROMPT
    if structured_context:
        system_content += f"\n\n{structured_context}\n"
    if memory_context:
        system_content += f"\n\n{memory_context}\n"
    if history_summary:
        system_content += f"\n\n{history_summary}\n"
    if context:
        system_content += f"\n\n## 相关知识库内容\n{context}\n"
    messages = [{"role": "system", "content": system_content}]
    messages.extend([msg.model_dump() for msg in recent_messages])
    messages.append({"role": "user", "content": user_input})
    return messages


async def retrieve_context(user_input: str) -> str:
    try:
        from backend.rag.rag_tool import get_rag_tool
        rag_tool = get_rag_tool()
        return await rag_tool.search(query=user_input, top_k=3, sources=None)
    except Exception as e:
        logger.warning(f"RAG 检索失败: {e}")
        return ""


async def execute_and_stream(websocket: WebSocket, agent, input_messages: list[dict], conversation_history: list[ConversationMessage], user_input: str) -> None:
    logger.info(f"开始流式执行 MultiAgentGraph... (历史消息数：{len(conversation_history)})")
    try:
        actual_user_input = user_input
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
        if system_parts or history_parts:
            composed_sections = []
            if system_parts:
                composed_sections.append("## 系统与上下文\n" + "\n\n".join(system_parts))
            if history_parts:
                composed_sections.append("## 最近对话历史\n" + "\n".join(history_parts[:-1]))
            composed_sections.append(f"## 当前用户问题\n{user_input}")
            actual_user_input = "\n\n".join(section for section in composed_sections if section.strip())
        final_content = None
        event_count = 0
        async for event in agent.stream_events(user_request=actual_user_input, enable_search=True, enable_visualization=True, style="friendly"):
            await websocket.send_json(event)
            event_count += 1
            if event.get("type") == "complete":
                final_content = event.get("final_content", "")
        logger.info(f"Agent 执行完成，共 {event_count} 个事件")
        if final_content:
            await websocket.send_json({"type": "final", "content": final_content})
            update_conversation_history(conversation_history, user_input, final_content)
        else:
            await websocket.send_json({"type": "error", "message": "未获取到响应"})
    except asyncio.CancelledError:
        logger.warning("Agent 执行被取消（客户端断开连接）")
        raise
    except Exception as e:
        logger.error(f"Agent 执行出错：{e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": str(e)})


def update_conversation_history(conversation_history: list[ConversationMessage], user_input: str, ai_response: str) -> None:
    conversation_history.append(ConversationMessage(role="user", content=user_input))
    conversation_history.append(ConversationMessage(role="assistant", content=ai_response))
    logger.info(f"当前对话历史：{len(conversation_history)} 条消息")


async def safe_send_error(websocket: WebSocket, error: Exception) -> None:
    try:
        await websocket.send_json({"type": "error", "message": str(error)})
    except Exception:
        pass


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG, log_level=settings.LOG_LEVEL.lower())
