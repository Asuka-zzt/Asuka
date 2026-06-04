"""WebRTC realtime chat signaling routes."""

from fastapi import APIRouter, HTTPException

from asuka.core.voice.manager import SESSION_TTL_SECONDS, realtime_session_manager
from asuka.core.voice.model import (
    CreateRealtimeSessionRequest,
    CreateRealtimeSessionResponse,
    IceCandidateMessage,
    SDPMessage,
)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


@router.post("/sessions")
async def create_realtime_session(
    req: CreateRealtimeSessionRequest,
) -> CreateRealtimeSessionResponse:
    """Allocate a realtime session before WebRTC SDP negotiation."""
    try:
        session = await realtime_session_manager.create(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateRealtimeSessionResponse(
        session_id=session.session_id,
        conversation_id=session.conversation_id,
        expires_in=SESSION_TTL_SECONDS,
    )


@router.post("/sessions/{session_id}/offer")
async def attach_offer(session_id: str, offer: SDPMessage) -> SDPMessage:
    """Accept a browser SDP offer and return the backend SDP answer."""
    session = realtime_session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="realtime session not found")
    try:
        answer = await realtime_session_manager.attach_offer(
            session_id,
            sdp=offer.sdp,
            sdp_type=offer.type,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"WebRTC offer failed: {exc}") from exc
    return SDPMessage(sdp=answer.sdp, type="answer")


@router.post("/sessions/{session_id}/ice")
async def add_ice_candidate(session_id: str, candidate: IceCandidateMessage) -> dict[str, bool]:
    """Accept a trickle ICE candidate.

    The MVP frontend sends a complete offer after ICE gathering, so this endpoint
    is intentionally a no-op compatibility hook for future trickle support.
    """
    if realtime_session_manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="realtime session not found")
    _ = candidate
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def close_realtime_session(session_id: str) -> dict[str, bool]:
    """Close and remove a realtime session."""
    closed = await realtime_session_manager.close(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="realtime session not found")
    return {"ok": True}
