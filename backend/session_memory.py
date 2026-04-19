"""会话持久化、长期记忆、动态摘要与上下文压缩模块。"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import get_settings
from backend.logger import get_logger
from backend.schemas import ConversationMessage

logger = get_logger(__name__)
settings = get_settings()


class SessionMemoryStore:
    CITIES = {"上海", "北京", "苏州", "深圳", "广州", "杭州", "南京", "成都", "重庆", "西安", "武汉", "长沙", "青岛", "厦门"}
    PERSONAS = {"亲子", "情侣", "学生", "长者", "老人", "家庭"}
    ACCOMMODATIONS = {"民宿", "酒店", "青旅", "地铁", "市中心"}
    FOOD_PREFS = {"清淡", "本地菜", "素食"}
    FOOD_AVOIDS = {"不吃辣", "忌口", "不吃海鲜", "不吃牛肉", "不吃羊肉"}

    def __init__(self):
        self.base_dir: Path = settings.SESSION_MEMORY_DIR
        self.sessions_dir = self.base_dir / "sessions"
        self.users_dir = self.base_dir / "users"
        self.index_file = self.base_dir / "user_sessions.json"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self.index_file.write_text("{}", encoding="utf-8")

    def create_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex[:12]}"

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _user_path(self, user_id: str) -> Path:
        return self.users_dir / f"{user_id}.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取 JSON 失败: {path}, error={e}")
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._read_json(self._session_path(session_id), None)

    def load_messages(self, session_id: str) -> List[ConversationMessage]:
        data = self.load_session(session_id)
        if not data:
            return []
        return [ConversationMessage(**item) for item in data.get("messages", [])]

    def _extract_memory(self, text: str) -> Dict[str, Any]:
        result = {
            "departure_city": None,
            "destinations": [],
            "budget_max": None,
            "days": None,
            "accommodation_preferences": [],
            "food_preferences": [],
            "food_avoidances": [],
            "travel_personas": [],
        }
        for city in self.CITIES:
            if f"从{city}出发" in text or text.startswith(f"{city}出发"):
                result["departure_city"] = city
            if f"去{city}" in text or f"到{city}" in text or f"玩{city}" in text:
                result["destinations"].append(city)
        budget_match = re.search(r"(?:预算|人均)?\s*(\d{3,6})\s*(?:元|块|以内|以下)?", text)
        if budget_match:
            result["budget_max"] = int(budget_match.group(1))
        day_match = re.search(r"(\d+)\s*(?:天|日游)", text)
        if day_match:
            result["days"] = int(day_match.group(1))
        for item in self.ACCOMMODATIONS:
            if item in text:
                result["accommodation_preferences"].append(item)
        for item in self.FOOD_PREFS:
            if item in text:
                result["food_preferences"].append(item)
        for item in self.FOOD_AVOIDS:
            if item in text:
                result["food_avoidances"].append(item)
        for item in self.PERSONAS:
            if item in text:
                result["travel_personas"].append("长者" if item == "老人" else item)
        return result

    def _extract_structured_context(self, messages: List[ConversationMessage]) -> Dict[str, Any]:
        structured = {
            "departure_city": None,
            "destinations": [],
            "budget_max": None,
            "days": None,
            "travel_personas": [],
            "accommodation_preferences": [],
            "food_avoidances": [],
            "confirmed_items": [],
        }
        for msg in messages:
            extracted = self._extract_memory(msg.content)
            if extracted.get("departure_city"):
                structured["departure_city"] = extracted["departure_city"]
            if extracted.get("budget_max") is not None:
                structured["budget_max"] = extracted["budget_max"]
            if extracted.get("days") is not None:
                structured["days"] = extracted["days"]
            for key in ["destinations", "travel_personas", "accommodation_preferences", "food_avoidances"]:
                current = set(structured.get(key, []))
                current.update(extracted.get(key, []))
                structured[key] = sorted(current)
            content = msg.content
            if any(token in content for token in ["已定", "确认", "确定", "选择了"]):
                structured["confirmed_items"].append(content[:80])
        structured["confirmed_items"] = structured["confirmed_items"][-5:]
        return structured

    def _build_summary(self, messages: List[ConversationMessage]) -> str:
        if not settings.ENABLE_DYNAMIC_SUMMARY:
            return ""
        window = settings.CONTEXT_WINDOW_MESSAGES
        if len(messages) <= window:
            return ""
        old_messages = messages[:-window]
        user_points = []
        assistant_points = []
        for msg in old_messages:
            text = re.sub(r"\s+", " ", msg.content).strip()
            if not text:
                continue
            snippet = text[:80]
            if msg.role == "user":
                user_points.append(snippet)
            elif msg.role == "assistant":
                assistant_points.append(snippet)
        lines = ["## 历史对话摘要"]
        if user_points:
            lines.append(f"- 用户曾提出：{'；'.join(user_points[-3:])}")
        if assistant_points:
            lines.append(f"- 系统曾回复：{'；'.join(assistant_points[-3:])}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def save_session(self, session_id: str, user_id: Optional[str], messages: List[ConversationMessage]) -> None:
        if not settings.ENABLE_SESSION_PERSISTENCE:
            return
        now = datetime.now().isoformat()
        existing = self.load_session(session_id) or {}
        created_at = existing.get("created_at", now)
        summary = self._build_summary(messages)
        structured_context = self._extract_structured_context(messages)
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": created_at,
            "updated_at": now,
            "messages": [m.model_dump() for m in messages],
            "summary": summary,
            "structured_context": structured_context,
            "last_plan": existing.get("last_plan"),
        }
        self._write_json(self._session_path(session_id), payload)
        if user_id:
            self._bind_session_to_user(user_id, session_id, now)

    def _bind_session_to_user(self, user_id: str, session_id: str, updated_at: str) -> None:
        index = self._read_json(self.index_file, {})
        sessions = index.get(user_id, [])
        sessions = [item for item in sessions if item.get("session_id") != session_id]
        sessions.insert(0, {"session_id": session_id, "updated_at": updated_at})
        index[user_id] = sessions[:50]
        self._write_json(self.index_file, index)

    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        index = self._read_json(self.index_file, {})
        return index.get(user_id, [])

    def load_user_memory(self, user_id: str) -> Dict[str, Any]:
        return self._read_json(
            self._user_path(user_id),
            {
                "user_id": user_id,
                "departure_city": None,
                "destinations": [],
                "budget_min": None,
                "budget_max": None,
                "accommodation_preferences": [],
                "food_preferences": [],
                "food_avoidances": [],
                "travel_personas": [],
                "updated_at": None,
            },
        )

    def update_user_memory_from_text(self, user_id: Optional[str], text: str) -> None:
        if not settings.ENABLE_LONG_TERM_MEMORY or not user_id:
            return
        memory = self.load_user_memory(user_id)
        extracted = self._extract_memory(text)
        if extracted.get("departure_city"):
            memory["departure_city"] = extracted["departure_city"]
        if extracted.get("budget_max") is not None:
            memory["budget_max"] = extracted["budget_max"]
        for key in ["destinations", "accommodation_preferences", "food_preferences", "food_avoidances", "travel_personas"]:
            current = set(memory.get(key, []))
            current.update(extracted.get(key, []))
            memory[key] = sorted(current)
        memory["updated_at"] = datetime.now().isoformat()
        self._write_json(self._user_path(user_id), memory)

    def build_memory_context(self, user_id: Optional[str]) -> str:
        if not settings.ENABLE_LONG_TERM_MEMORY or not user_id:
            return ""
        memory = self.load_user_memory(user_id)
        lines = []
        if memory.get("departure_city"):
            lines.append(f"- 常用出发地：{memory['departure_city']}")
        if memory.get("destinations"):
            lines.append(f"- 历史目的地偏好：{'、'.join(memory['destinations'])}")
        if memory.get("budget_max"):
            lines.append(f"- 常用预算上限：{memory['budget_max']} 元")
        if memory.get("accommodation_preferences"):
            lines.append(f"- 住宿偏好：{'、'.join(memory['accommodation_preferences'])}")
        if memory.get("food_preferences"):
            lines.append(f"- 饮食偏好：{'、'.join(memory['food_preferences'])}")
        if memory.get("food_avoidances"):
            lines.append(f"- 饮食禁忌：{'、'.join(memory['food_avoidances'])}")
        if memory.get("travel_personas"):
            lines.append(f"- 常见出行人群：{'、'.join(memory['travel_personas'])}")
        if not lines:
            return ""
        return "## 用户长期记忆\n" + "\n".join(lines)

    def build_session_context(self, session_id: Optional[str], messages: List[ConversationMessage]) -> Dict[str, Any]:
        data = self.load_session(session_id) if session_id else None
        summary = ""
        structured_context: Dict[str, Any] = {}
        if data:
            summary = data.get("summary", "") or ""
            structured_context = data.get("structured_context", {}) or {}
        if not summary and messages:
            summary = self._build_summary(messages)
        if not structured_context and messages:
            structured_context = self._extract_structured_context(messages)
        recent_messages = messages[-settings.CONTEXT_WINDOW_MESSAGES:] if settings.ENABLE_CONTEXT_COMPRESSION else messages
        lines = []
        if structured_context.get("departure_city"):
            lines.append(f"- 当前会话出发地：{structured_context['departure_city']}")
        if structured_context.get("destinations"):
            lines.append(f"- 当前会话目的地：{'、'.join(structured_context['destinations'])}")
        if structured_context.get("budget_max"):
            lines.append(f"- 当前会话预算上限：{structured_context['budget_max']} 元")
        if structured_context.get("days"):
            lines.append(f"- 当前会话旅行时长：{structured_context['days']} 天")
        if structured_context.get("travel_personas"):
            lines.append(f"- 当前会话出行人群：{'、'.join(structured_context['travel_personas'])}")
        if structured_context.get("accommodation_preferences"):
            lines.append(f"- 当前会话住宿要求：{'、'.join(structured_context['accommodation_preferences'])}")
        if structured_context.get("food_avoidances"):
            lines.append(f"- 当前会话饮食禁忌：{'、'.join(structured_context['food_avoidances'])}")
        if structured_context.get("confirmed_items"):
            lines.append(f"- 已确认内容：{'；'.join(structured_context['confirmed_items'])}")
        structured_text = "## 当前会话关键约束\n" + "\n".join(lines) if lines else ""
        return {
            "summary": summary,
            "structured_text": structured_text,
            "recent_messages": recent_messages,
            "structured_context": structured_context,
        }


_store: Optional[SessionMemoryStore] = None


def get_session_memory_store() -> SessionMemoryStore:
    global _store
    if _store is None:
        _store = SessionMemoryStore()
    return _store
