"""POST /api/tts — synthesize assistant text to speech audio."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from asukabot.api.provider import tts as tts_provider
from asukabot.config import get_settings

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str | None = None


@router.post("/api/tts")
async def tts(req: TTSRequest) -> Response:
    """Return MP3 audio for the provided text."""
    text = req.text.strip()
    settings = get_settings()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")
    if len(text) > settings.tts_max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"text exceeds {settings.tts_max_chars} characters",
        )

    try:
        audio = await tts_provider.synthesize_speech(text, req.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="TTS synthesis failed") from exc
    return Response(content=audio, media_type="audio/mpeg")
