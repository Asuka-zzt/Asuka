"""TTS provider abstraction backed by edge-tts."""

from collections.abc import AsyncIterator
from typing import Any, cast

import edge_tts

from asuka.config import get_settings


def resolve_voice(voice: str | None = None, language: str | None = None) -> str:
    """按显式 voice / language / 默认配置解析 edge-tts voice。"""
    settings = get_settings()
    if voice:
        return voice
    if language:
        return settings.tts_voices.get(language, settings.tts_voice)
    return settings.tts_voice


async def iter_speech_chunks(
    text: str,
    voice: str | None = None,
    language: str | None = None,
) -> AsyncIterator[bytes]:
    """Yield MP3 audio chunks using the configured edge-tts voice."""
    settings = get_settings()
    communicate = edge_tts.Communicate(
        text,
        resolve_voice(voice, language),
        rate=settings.tts_rate,
        volume=settings.tts_volume,
        pitch=settings.tts_pitch,
    )

    async for chunk in communicate.stream():
        typed_chunk = cast(dict[str, Any], chunk)
        if typed_chunk.get("type") == "audio":
            data = typed_chunk.get("data")
            if isinstance(data, bytes):
                yield data


async def synthesize_speech(
    text: str,
    voice: str | None = None,
    language: str | None = None,
) -> bytes:
    """Synthesize text into MP3 bytes using the configured edge-tts voice."""
    audio_chunks = [
        chunk async for chunk in iter_speech_chunks(text, voice, language)
    ]
    if not audio_chunks:
        raise RuntimeError("TTS did not return audio data")

    return b"".join(audio_chunks)
