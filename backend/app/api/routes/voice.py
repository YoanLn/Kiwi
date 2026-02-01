"""
WebSocket endpoint for voice chat using Gemini Live API.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.config import settings
from app.schemas.workflow import WorkflowType
from app.services.voice_service import get_voice_service, VoiceSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceConnectionManager:
    """Manages WebSocket connections for voice chat."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info("Voice WebSocket connected: %s", session_id)

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info("Voice WebSocket disconnected: %s", session_id)

    async def send_audio(self, session_id: str, audio_data: bytes):
        """Send audio data to the client."""
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_json(
                {
                    "type": "audio",
                    "data": base64.b64encode(audio_data).decode("utf-8"),
                }
            )

    async def send_transcription(self, session_id: str, role: str, text: str):
        """Send transcription to the client."""
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_json(
                {
                    "type": "transcription",
                    "role": role,
                    "text": text,
                }
            )

    async def send_status(self, session_id: str, status: str, message: str = ""):
        """Send status update to the client."""
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_json(
                {
                    "type": "status",
                    "status": status,
                    "message": message,
                }
            )


voice_manager = VoiceConnectionManager()


@router.websocket("/ws/{session_id}")
async def voice_chat_websocket(
    websocket: WebSocket,
    session_id: str,
    workflow_type: str = Query(default="insurance_claim"),
):
    """
    WebSocket endpoint for real-time voice chat.

    Protocol:
    - Client sends: {"type": "audio", "data": "<base64 PCM audio>"}
    - Client sends: {"type": "text", "content": "<text message>"}
    - Server sends: {"type": "audio", "data": "<base64 PCM audio>"}
    - Server sends: {"type": "transcription", "role": "user|assistant", "text": "..."}
    - Server sends: {"type": "status", "status": "ready|processing|error", "message": "..."}
    """
    await voice_manager.connect(websocket, session_id)

    voice_service = get_voice_service()
    session: VoiceSession | None = None

    try:
        try:
            wf_type = WorkflowType(workflow_type)
        except ValueError:
            wf_type = WorkflowType.INSURANCE_CLAIM

        async def on_audio_response(audio_data: bytes):
            await voice_manager.send_audio(session_id, audio_data)

        async def on_transcription(role: str, text: str):
            await voice_manager.send_transcription(session_id, role, text)

        try:
            session = await voice_service.create_session(
                session_id=session_id,
                workflow_type=wf_type,
                on_audio_response=on_audio_response,
                on_transcription=on_transcription,
            )
        except Exception as exc:  # pragma: no cover - defensive logging for runtime issues
            logger.error("Failed to create voice session: %s", exc)
            await voice_manager.send_status(
                session_id,
                "error",
                "Voice session failed to start (check GEMINI_API_KEY/model).",
            )
            return

        await voice_manager.send_status(session_id, "ready", "Voice session started")

        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "audio":
                    audio_data = base64.b64decode(message.get("data", ""))
                    if audio_data:
                        await session.send_audio(audio_data)

                elif msg_type == "text":
                    text = message.get("content", "").strip()
                    if text:
                        await session.send_text(text)

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                await voice_manager.send_status(
                    session_id, "error", "Invalid JSON format"
                )
            except Exception as exc:
                logger.error("Error processing voice message: %s", exc)
                await voice_manager.send_status(session_id, "error", str(exc))

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected: %s", session_id)
    except Exception as exc:
        logger.error("Voice WebSocket error: %s", exc)
    finally:
        voice_manager.disconnect(session_id)
        if session:
            await voice_service.close_session(session_id)


@router.get("/info")
async def voice_info():
    """Get information about the voice API."""
    return {
        "model": settings.GEMINI_LIVE_MODEL or settings.VERTEX_AI_LIVE_MODEL,
        "input_format": "Raw 16-bit PCM audio at 16kHz, little-endian",
        "output_format": "Raw 16-bit PCM audio at 24kHz, little-endian",
        "websocket_endpoint": "/api/v1/voice/ws/{session_id}?workflow_type=insurance_claim",
    }
