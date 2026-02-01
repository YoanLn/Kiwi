from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    """
    Chat request schema.
    Note: user_id is NOT in request body - it comes from JWT auth token.
    This is a critical security measure.
    """
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    response: str
    sources: List[str] = []
    timestamp: datetime
