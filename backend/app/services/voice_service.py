"""
Voice Service using Gemini Live API for speech-to-speech conversations.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable

import os

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.workflow import WorkflowType

logger = logging.getLogger(__name__)


VOICE_SYSTEM_PROMPTS = {
    WorkflowType.INSURANCE_CLAIM: """You are a helpful insurance claims assistant for a French insurance company.
Your role is to help customers file claims and answer questions about the claims process.
Be friendly, professional, and empathetic. Many customers may be stressed after an incident.
Keep responses concise and natural for voice conversation.
Always respond in the same language the customer uses (French or English).""",
    WorkflowType.FILE_MANAGEMENT: """You are a helpful insurance file management assistant for a French insurance company.
Your role is to help customers understand their policies and manage their insurance files.
Be friendly, professional, and patient.
Keep responses concise and natural for voice conversation.
Always respond in the same language the customer uses (French or English).""",
}


class VoiceSession:
    """Manages a single voice conversation session."""

    def __init__(
        self,
        session_id: str,
        workflow_type: WorkflowType,
        on_audio_response: Optional[Callable[[bytes], None]] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None,
    ):
        self.session_id = session_id
        self.workflow_type = workflow_type
        self.on_audio_response = on_audio_response
        self.on_transcription = on_transcription

        self.model = settings.GEMINI_LIVE_MODEL or settings.VERTEX_AI_LIVE_MODEL
        if not self.model:
            raise ValueError("GEMINI_LIVE_MODEL is not configured")

        api_key = (
            settings.GEMINI_API_KEY
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not api_key:
            raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) is required for Gemini API")

        self.client = genai.Client(api_key=api_key)

        self.session = None
        self.is_active = False
        self._receive_task: Optional[asyncio.Task] = None

        logger.info(
            "Voice session %s created for %s with model %s (Gemini API)",
            session_id,
            workflow_type.value,
            self.model,
        )

    async def start(self):
        """Start the voice session."""
        system_prompt = VOICE_SYSTEM_PROMPTS.get(
            self.workflow_type,
            VOICE_SYSTEM_PROMPTS[WorkflowType.INSURANCE_CLAIM],
        )

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO", "TEXT"],
            system_instruction=types.Content(
                role="user",
                parts=[types.Part(text=system_prompt)],
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede",
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        try:
            self.session = await self.client.aio.live.connect(
                model=self.model,
                config=config,
            )
            self.is_active = True
            self._receive_task = asyncio.create_task(self._receive_responses())
            logger.info("Voice session %s started", self.session_id)
        except Exception as exc:
            logger.error("Failed to start voice session: %s", exc)
            raise

    async def _receive_responses(self):
        """Background task to receive and process responses from Gemini."""
        try:
            async for message in self.session.receive():
                if not self.is_active:
                    break

                server_content = message.server_content
                if not server_content:
                    continue

                if server_content.interrupted:
                    logger.debug("Session %s: Response interrupted", self.session_id)
                    continue

                # Handle model audio/text responses
                if server_content.model_turn and server_content.model_turn.parts:
                    for part in server_content.model_turn.parts:
                        # Handle audio output
                        if part.inline_data and self.on_audio_response:
                            await self._safe_callback(
                                self.on_audio_response,
                                part.inline_data.data,
                            )

                # Handle output transcription (assistant's speech transcribed to text)
                if (
                    hasattr(server_content, "output_transcription")
                    and server_content.output_transcription
                    and server_content.output_transcription.text
                ):
                    if self.on_transcription:
                        await self._safe_callback(
                            self.on_transcription,
                            "assistant",
                            server_content.output_transcription.text,
                        )

                # Handle input transcription (user's speech transcribed to text)
                if (
                    hasattr(server_content, "input_transcription")
                    and server_content.input_transcription
                    and server_content.input_transcription.text
                ):
                    if self.on_transcription:
                        await self._safe_callback(
                            self.on_transcription,
                            "user",
                            server_content.input_transcription.text,
                        )

        except asyncio.CancelledError:
            logger.debug("Receive task cancelled for session %s", self.session_id)
        except Exception as exc:
            logger.error("Error receiving responses: %s", exc)

    async def _safe_callback(self, callback, *args):
        """Safely execute callback, handling both sync and async functions."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.error("Callback error: %s", exc)

    async def send_audio(self, audio_data: bytes):
        """Send audio data to the session."""
        if not self.is_active or not self.session:
            logger.warning("Cannot send audio: session %s not active", self.session_id)
            return

        try:
            await self.session.send_realtime_input(
                audio=types.Blob(
                    data=audio_data,
                    mime_type="audio/pcm;rate=16000",
                )
            )
        except Exception as exc:
            logger.error("Error sending audio: %s", exc)
            raise

    async def send_text(self, text: str):
        """Send text message to the session."""
        if not self.is_active or not self.session:
            logger.warning("Cannot send text: session %s not active", self.session_id)
            return

        try:
            await self.session.send_client_content(
                content=types.Content(
                    role="user",
                    parts=[types.Part(text=text)],
                ),
                turn_complete=True,
            )
        except Exception as exc:
            logger.error("Error sending text: %s", exc)
            raise

    async def stop(self):
        """Stop the voice session."""
        self.is_active = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.session:
            try:
                await self.session.close()
            except Exception as exc:
                logger.error("Error closing session: %s", exc)

        logger.info("Voice session %s stopped", self.session_id)


class VoiceService:
    """Service for managing voice conversations."""

    def __init__(self):
        self.sessions: dict[str, VoiceSession] = {}
        logger.info("Voice Service initialized")

    async def create_session(
        self,
        session_id: str,
        workflow_type: WorkflowType,
        on_audio_response: Optional[Callable[[bytes], None]] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None,
    ) -> VoiceSession:
        """Create a new voice session."""
        if session_id in self.sessions:
            await self.close_session(session_id)

        session = VoiceSession(
            session_id=session_id,
            workflow_type=workflow_type,
            on_audio_response=on_audio_response,
            on_transcription=on_transcription,
        )

        await session.start()
        self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get an existing voice session."""
        return self.sessions.get(session_id)

    async def close_session(self, session_id: str):
        """Close and remove a voice session."""
        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            await session.stop()

    async def close_all_sessions(self):
        """Close all active sessions."""
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)


_voice_service: Optional[VoiceService] = None


def get_voice_service() -> VoiceService:
    """Get the voice service instance."""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service
