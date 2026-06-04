"""In-memory lifecycle manager for realtime voice sessions."""

import time
import uuid

from aiortc import RTCSessionDescription

from asuka.core.agent.presets import resolve_agent_config
from asuka.core.voice.model import CreateRealtimeSessionRequest
from asuka.core.voice.session import RealtimeVoiceSession

SESSION_TTL_SECONDS = 300


class RealtimeSessionManager:
    """Manage active realtime sessions for the FastAPI process."""

    def __init__(self) -> None:
        self._sessions: dict[str, RealtimeVoiceSession] = {}

    async def create(self, req: CreateRealtimeSessionRequest) -> RealtimeVoiceSession:
        self.cleanup_expired()
        agent_config = resolve_agent_config(req.persona_id, req.level)
        session = RealtimeVoiceSession(
            session_id=f"rt_{uuid.uuid4().hex}",
            conversation_id=req.conversation_id,
            agent_config=agent_config,
            language=req.language,
            voice=req.voice,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> RealtimeVoiceSession | None:
        return self._sessions.get(session_id)

    async def attach_offer(
        self,
        session_id: str,
        *,
        sdp: str,
        sdp_type: str,
    ) -> RTCSessionDescription:
        session = self._sessions[session_id]
        return await session.attach_offer(RTCSessionDescription(sdp=sdp, type=sdp_type))

    async def close(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        await session.close()
        return True

    def cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_seen_at > SESSION_TTL_SECONDS
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


realtime_session_manager = RealtimeSessionManager()

