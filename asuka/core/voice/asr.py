"""ASR providers for realtime voice."""

import asyncio
from typing import Protocol

import numpy as np

from asuka.config import Settings, get_settings


class AsrProvider(Protocol):
    """Speech-to-text provider contract."""

    async def transcribe(self, pcm: bytes, *, sample_rate: int, language: str | None) -> str:
        """Transcribe mono s16 PCM into text."""


def normalize_language(language: str | None) -> str | None:
    """Map app language names to provider language codes."""
    if not language:
        return None
    value = language.lower()
    return {
        "chinese": "zh",
        "zh": "zh",
        "zh-cn": "zh",
        "english": "en",
        "en": "en",
        "japanese": "ja",
        "ja": "ja",
        "jp": "ja",
    }.get(value, value)


class FasterWhisperAsrProvider:
    """Local faster-whisper ASR provider."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model: object | None = None
        self._lock = asyncio.Lock()

    async def transcribe(self, pcm: bytes, *, sample_rate: int, language: str | None) -> str:
        """Run faster-whisper over a complete speech segment."""
        if not pcm:
            return ""
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return ""

        model = await self._get_model()
        return await asyncio.to_thread(
            self._transcribe_sync,
            model,
            samples,
            normalize_language(language),
        )

    async def _get_model(self) -> object:
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.settings.asr_model,
                    device=self.settings.asr_device,
                    compute_type=self.settings.asr_compute_type,
                )
        return self._model

    def _transcribe_sync(
        self,
        model: object,
        samples: np.ndarray,
        language: str | None,
    ) -> str:
        segments, _info = model.transcribe(  # type: ignore[attr-defined]
            samples,
            language=language,
            vad_filter=False,
            beam_size=5,
        )
        return "".join(segment.text for segment in segments).strip()


_asr_provider: AsrProvider | None = None


def get_asr_provider() -> AsrProvider:
    """Return the process-wide ASR provider."""
    global _asr_provider
    if _asr_provider is None:
        _asr_provider = FasterWhisperAsrProvider()
    return _asr_provider


def set_asr_provider(provider: AsrProvider | None) -> None:
    """Override the process-wide ASR provider for tests."""
    global _asr_provider
    _asr_provider = provider
