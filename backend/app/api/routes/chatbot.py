from datetime import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import User, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.models.chat_message import ChatMessage
from app.schemas.chatbot import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Chat with the AI assistant about insurance terms and processes.
    Uses RAG (Retrieval-Augmented Generation) with Vertex AI.

    Demo mode: allows unauthenticated access and uses a fixed user_id.
    For production, require JWT auth and remove the fallback.
    """
    # Initialize RAG service
    rag_service = RAGService()

    # Generate session ID if not provided
    session_id = chat_request.session_id or str(uuid.uuid4())

    if not settings.DEMO_MODE and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Demo fallback: allow unauthenticated usage with a fixed user_id
    user_id = current_user.user_id if current_user else settings.DEMO_USER_ID

    try:
        # Get AI response using RAG
        result = await rag_service.generate_response(
            query=chat_request.message,
            user_id=user_id,  # From auth token
            session_id=session_id
        )

        # Save chat message to database
        chat_message = ChatMessage(
            session_id=session_id,
            user_id=user_id,  # From auth token
            message=chat_request.message,
            response=result["response"],
            sources_used=result.get("sources")
        )

        db.add(chat_message)
        db.commit()
        db.refresh(chat_message)

        return ChatResponse(
            session_id=session_id,
            message=chat_request.message,
            response=result["response"],
            sources=result.get("sources_list", []),
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )


@router.post("/feedback")
async def submit_feedback(
    message_id: int,
    is_helpful: bool,
    db: Session = Depends(get_db)
):
    """Submit feedback on a chat response"""
    chat_message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()

    if not chat_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    chat_message.is_helpful = is_helpful
    db.commit()

    return {"status": "success", "message": "Feedback submitted"}
