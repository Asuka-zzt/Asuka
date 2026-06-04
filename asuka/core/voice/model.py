"""Schemas for realtime voice signaling and data-channel events."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRealtimeSessionRequest(BaseModel):
    """Create a realtime WebRTC session bound to a conversation."""

    conversation_id: str = Field(..., min_length=1)
    persona_id: str | None = None
    level: str | None = None
    language: str | None = None
    voice: str | None = None


class CreateRealtimeSessionResponse(BaseModel):
    """Response returned after allocating a realtime session."""

    session_id: str
    conversation_id: str
    expires_in: int


class SDPMessage(BaseModel):
    """WebRTC SDP offer/answer payload."""

    sdp: str
    type: Literal["offer", "answer"]


class IceCandidateMessage(BaseModel):
    """Trickle ICE candidate payload."""

    candidate: str | None = None
    sdpMid: str | None = None
    sdpMLineIndex: int | None = None


class RealtimeEvent(BaseModel):
    """DataChannel event envelope shared by frontend and backend."""

    type: str
    id: str
    conversationId: str
    sessionId: str
    createdAt: int
    turnId: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

