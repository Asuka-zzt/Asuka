"""POST /api/tts — synthesize assistant text to speech audio."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from asukabot.api.provider import tts as tts_provider
from asukabot.config import get_settings

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str | None = None


def _validate_request(req: TTSRequest) -> str:
    text = req.text.strip()
    settings = get_settings()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")
    if len(text) > settings.tts_max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"text exceeds {settings.tts_max_chars} characters",
        )
    return text


@router.post("/api/tts")
async def tts(req: TTSRequest) -> Response:
    """Return MP3 audio for the provided text."""
    text = _validate_request(req)
    try:
        audio = await tts_provider.synthesize_speech(text, req.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="TTS synthesis failed") from exc
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/api/tts/stream")
async def stream_tts(req: TTSRequest) -> StreamingResponse:
    """Stream MP3 audio chunks for the provided text."""
    text = _validate_request(req)

    async def audio_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in tts_provider.iter_speech_chunks(text, req.voice):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("TTS synthesis failed") from exc

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")
