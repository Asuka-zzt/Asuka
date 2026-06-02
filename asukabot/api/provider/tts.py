"""TTS provider abstraction backed by edge-tts."""

from typing import Any, cast

import edge_tts

from asukabot.config import get_settings


async def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Synthesize text into MP3 bytes using the configured edge-tts voice."""
    settings = get_settings()
    communicate = edge_tts.Communicate(
        text,
        voice or settings.tts_voice,
        rate=settings.tts_rate,
        volume=settings.tts_volume,
        pitch=settings.tts_pitch,
    )

    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        typed_chunk = cast(dict[str, Any], chunk)
        if typed_chunk.get("type") == "audio":
            data = typed_chunk.get("data")
            if isinstance(data, bytes):
                audio_chunks.append(data)

    if not audio_chunks:
        raise RuntimeError("TTS did not return audio data")

    return b"".join(audio_chunks)
