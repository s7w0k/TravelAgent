from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logger import get_logger
from backend.session_memory import get_session_memory_store

logger = get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["Memory"])


class SessionDetailResponse(BaseModel):
    session_id: str
    user_id: str | None
    created_at: str
    updated_at: str
    messages: List[Dict[str, Any]]
    summary: str = ""
    last_plan: Dict[str, Any] | None = None


class UserSessionsResponse(BaseModel):
    user_id: str
    sessions: List[Dict[str, Any]]


class UserMemoryResponse(BaseModel):
    user_id: str
    departure_city: str | None = None
    destinations: List[str] = []
    budget_min: int | None = None
    budget_max: int | None = None
    accommodation_preferences: List[str] = []
    food_preferences: List[str] = []
    food_avoidances: List[str] = []
    travel_personas: List[str] = []
    updated_at: str | None = None


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: str):
    store = get_session_memory_store()
    data = store.load_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionDetailResponse(**data)


@router.get("/users/{user_id}/sessions", response_model=UserSessionsResponse)
async def get_user_sessions(user_id: str):
    store = get_session_memory_store()
    return UserSessionsResponse(user_id=user_id, sessions=store.get_user_sessions(user_id))


@router.get("/users/{user_id}/memory", response_model=UserMemoryResponse)
async def get_user_memory(user_id: str):
    store = get_session_memory_store()
    return UserMemoryResponse(**store.load_user_memory(user_id))
