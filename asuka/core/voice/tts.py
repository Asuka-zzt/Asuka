"""Realtime TTS providers and text segmentation."""

import asyncio
import base64
import io
import json
import re
import struct
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Protocol

import av
import numpy as np
from av.audio.resampler import AudioResampler
from av.container.input import InputContainer
from av.error import FFmpegError
from websockets.asyncio.client import connect as websocket_connect

from asuka.config import Settings, get_settings

SENTENCE_END_RE = re.compile(r"(.+?[。！？!?；;\n]+)(?=\s*|$)", re.DOTALL)
EAGER_SENTENCE_END_RE = re.compile(r"(.+?[。！？!?；;，,、：:\n]+)(?=\s*|$)", re.DOTALL)
CONTROL_TAG_RE = re.compile(r"\[(?:emotion|expression|motion):[^\]]+\]", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
EAGER_SEGMENT_MIN_CHARS = 32


class VolcengineMessageType(IntEnum):
    """Volcengine audio protocol message types."""

    FULL_CLIENT_REQUEST = 0b0001
    FULL_SERVER_RESPONSE = 0b1001
    AUDIO_ONLY_RESPONSE = 0b1011
    ERROR_INFORMATION = 0b1111


class VolcengineSerializationMethod(IntEnum):
    """Volcengine audio protocol serialization methods."""

    RAW = 0b0000
    JSON = 0b0001


class VolcengineEventSend(IntEnum):
    """Events sent to Volcengine bidirectional TTS."""

    START_CONNECTION = 1
    FINISH_CONNECTION = 2
    START_SESSION = 100
    FINISH_SESSION = 102
    TASK_REQUEST = 200


class VolcengineEventReceive(IntEnum):
    """Events received from Volcengine bidirectional TTS."""

    CONNECTION_STARTED = 50
    CONNECTION_FAILED = 51
    CONNECTION_FINISHED = 52
    SESSION_STARTED = 150
    SESSION_FINISHED = 152
    SESSION_FAILED = 153
    TTS_SENTENCE_START = 350
    TTS_SENTENCE_END = 351
    TTS_RESPONSE = 352
    TTS_ENDED = 359
    SERVER_PROCESSING_ERROR = 55000001


@dataclass(frozen=True)
class SynthesizedPcm:
    """Mono s16 PCM synthesized by a TTS provider."""

    pcm: bytes
    sample_rate: int


class TtsProviderError(RuntimeError):
    """Raised when TTS cannot synthesize a segment."""


class RealtimeTtsProvider(Protocol):
    """Text-to-speech provider contract."""

    async def synthesize(self, text: str, *, language: str | None) -> SynthesizedPcm:
        """Synthesize text into mono s16 PCM."""


class StreamingRealtimeTtsProvider(RealtimeTtsProvider, Protocol):
    """Text-to-speech provider that can yield PCM chunks as they arrive."""

    def stream_synthesize(
        self,
        text: str,
        *,
        language: str | None,
    ) -> AsyncIterator[SynthesizedPcm]:
        """Synthesize text into a stream of mono s16 PCM chunks."""


class RealtimeTtsStream(Protocol):
    """A reusable TTS connection scoped to a single voice session."""

    async def render(self, text: str, *, language: str | None) -> SynthesizedPcm:
        """Synthesize one sentence, reusing the underlying connection."""

    async def aclose(self) -> None:
        """Tear down the underlying connection."""


class SessionScopedTtsProvider(RealtimeTtsProvider, Protocol):
    """A provider that can open a connection reused across one session's sentences."""

    def open_stream(self) -> RealtimeTtsStream:
        """Open a connection reused across all sentences of one voice session."""


def normalize_language(language: str | None) -> str:
    """Map app language names to model-map keys."""
    if not language:
        return "chinese"
    value = language.lower()
    return {
        "zh": "chinese",
        "zh-cn": "chinese",
        "cn": "chinese",
        "en": "english",
        "ja": "japanese",
        "jp": "japanese",
    }.get(value, value)


def clean_text_for_speech(text: str) -> str:
    """Remove markdown/control syntax that should not be spoken."""
    return (
        text.replace("```", " ")
        .replace("`", "")
        .replace("_", " ")
        .replace("*", "")
        .replace("#", "")
    )


def clean_sentence_for_speech(text: str) -> str:
    """Clean one sentence for TTS."""
    return (
        CONTROL_TAG_RE.sub(" ", text)
        .replace("\u200b", "")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def sentence_segments(
    buffer: str,
    *,
    force: bool = False,
    eager: bool = False,
    min_chars: int = EAGER_SEGMENT_MIN_CHARS,
) -> tuple[list[str], str]:
    """Split a streaming text buffer into complete spoken sentences."""
    segments: list[str] = []
    pos = 0
    pattern = EAGER_SENTENCE_END_RE if eager else SENTENCE_END_RE
    for match in pattern.finditer(buffer):
        segment = clean_sentence_for_speech(match.group(1)).strip()
        if segment:
            segments.append(segment)
        pos = match.end()

    remaining = buffer[pos:]
    if eager and len(remaining) >= min_chars:
        split_at = remaining.rfind(" ", 0, min_chars + 1)
        if split_at <= 0:
            split_at = min_chars
        segment = clean_sentence_for_speech(remaining[:split_at]).strip()
        if segment:
            segments.append(segment)
        remaining = remaining[split_at:]

    if force:
        segment = clean_sentence_for_speech(remaining).strip()
        if segment:
            segments.append(segment)
        remaining = ""

    return segments, remaining


class PiperTtsProvider:
    """Local Piper TTS provider."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._voices: dict[str, object] = {}
        self._lock = asyncio.Lock()

    async def synthesize(self, text: str, *, language: str | None) -> SynthesizedPcm:
        clean = self._clean(text)
        if not clean:
            return SynthesizedPcm(pcm=b"", sample_rate=self.settings.piper_sample_rate)

        voice = await self._get_voice(language)
        return await asyncio.to_thread(self._synthesize_sync, voice, clean)

    async def _get_voice(self, language: str | None) -> object:
        key = normalize_language(language)
        if key in self._voices:
            return self._voices[key]

        model_path = self.settings.piper_model_by_language.get(key)
        if not model_path:
            raise TtsProviderError(f"missing Piper model for language: {key}")
        if not Path(model_path).exists():
            raise TtsProviderError(f"Piper model not found: {model_path}")

        async with self._lock:
            if key not in self._voices:
                from piper import PiperVoice

                self._voices[key] = PiperVoice.load(model_path)
        return self._voices[key]

    def _synthesize_sync(self, voice: object, text: str) -> SynthesizedPcm:
        pcm = bytearray()
        sample_rate = self.settings.piper_sample_rate
        for chunk in voice.synthesize(text):  # type: ignore[attr-defined]
            sample_rate = int(chunk.sample_rate)
            pcm.extend(chunk.audio_int16_bytes)
        return SynthesizedPcm(pcm=bytes(pcm), sample_rate=sample_rate)

    def _clean(self, text: str) -> str:
        return URL_RE.sub(" ", clean_text_for_speech(text)).strip()


class EdgeTtsProvider:
    """Realtime provider backed by the existing edge-tts MP3 synthesizer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def synthesize(self, text: str, *, language: str | None) -> SynthesizedPcm:
        clean = self._clean(text)
        if not clean:
            return SynthesizedPcm(pcm=b"", sample_rate=self.settings.piper_sample_rate)

        from asuka.api.provider import tts as edge_tts_provider

        audio_bytes = await edge_tts_provider.synthesize_speech(clean, language=language)
        return compressed_audio_bytes_to_pcm(
            audio_bytes,
            target_sample_rate=self.settings.piper_sample_rate,
        )

    def _clean(self, text: str) -> str:
        return URL_RE.sub(" ", clean_text_for_speech(text)).strip()


class Qwen3TtsProvider:
    """DashScope Qwen3-TTS provider.

    This provider uses the non-streaming HTTP API per sentence. DashScope returns
    either an audio URL or base64 audio data, both decoded into mono s16 PCM.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def synthesize(self, text: str, *, language: str | None) -> SynthesizedPcm:
        clean = self._clean(text)
        if not clean:
            return SynthesizedPcm(pcm=b"", sample_rate=self.settings.piper_sample_rate)
        if not self.settings.dashscope_api_key:
            raise TtsProviderError("missing DASHSCOPE_API_KEY for Qwen3-TTS")

        audio_bytes = await asyncio.to_thread(self._request_audio_sync, clean, language)
        return wav_bytes_to_pcm(audio_bytes)

    def _request_audio_sync(self, text: str, language: str | None) -> bytes:
        payload = self._request_payload(text, language)
        request = urllib.request.Request(
            self.settings.qwen_tts_base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=self.settings.qwen_tts_timeout_seconds,
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TtsProviderError(f"Qwen3-TTS HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TtsProviderError(f"Qwen3-TTS request failed: {exc.reason}") from exc

        payload_obj = json.loads(body.decode("utf-8"))
        audio_obj = self._extract_audio(payload_obj)
        if "data" in audio_obj and audio_obj["data"]:
            return base64.b64decode(str(audio_obj["data"]))
        if "url" in audio_obj and audio_obj["url"]:
            return self._download_audio(str(audio_obj["url"]))
        raise TtsProviderError("Qwen3-TTS response has no audio data or url")

    def _request_payload(self, text: str, language: str | None) -> dict[str, Any]:
        language_key = normalize_language(language)
        language_type = self.settings.qwen_tts_language_type_by_language.get(language_key)
        parameters: dict[str, Any] = {"voice": self.settings.qwen_tts_voice}
        if language_type:
            parameters["language_type"] = language_type
        return {
            "model": self.settings.qwen_tts_model,
            "input": {
                "text": text,
            },
            "parameters": parameters,
        }

    def _extract_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        output = payload.get("output")
        if not isinstance(output, dict):
            raise TtsProviderError("Qwen3-TTS response missing output")
        audio = output.get("audio")
        if not isinstance(audio, dict):
            raise TtsProviderError("Qwen3-TTS response missing output.audio")
        return audio

    def _download_audio(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"Accept": "audio/wav,audio/*"})
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=self.settings.qwen_tts_timeout_seconds,
            ) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TtsProviderError(f"Qwen3-TTS audio download HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TtsProviderError(f"Qwen3-TTS audio download failed: {exc.reason}") from exc

    def _clean(self, text: str) -> str:
        return URL_RE.sub(" ", clean_text_for_speech(text)).strip()


class VolcengineTtsProvider:
    """Volcengine OpenSpeech V3 TTS provider.

    The provider uses the bidirectional WebSocket V3 API. It keeps the
    `synthesize()` API for fallback callers and exposes `stream_synthesize()`
    so realtime sessions can enqueue PCM chunks as they arrive.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def synthesize(self, text: str, *, language: str | None) -> SynthesizedPcm:
        sample_rate = self.settings.volcengine_tts_sample_rate
        chunks = bytearray()
        async for audio in self.stream_synthesize(text, language=language):
            sample_rate = audio.sample_rate
            chunks.extend(audio.pcm)
        return SynthesizedPcm(pcm=bytes(chunks), sample_rate=sample_rate)

    async def stream_synthesize(
        self,
        text: str,
        *,
        language: str | None,
    ) -> AsyncIterator[SynthesizedPcm]:
        clean = self._clean(text)
        sample_rate = self.settings.volcengine_tts_sample_rate
        if not clean:
            return
        if not (
            self.settings.volcengine_tts_api_key
            or (
                self.settings.volcengine_tts_app_id
                and self.settings.volcengine_tts_access_key
            )
        ):
            raise TtsProviderError(
                "missing VOLCENGINE_TTS_API_KEY or "
                "VOLCENGINE_TTS_APP_ID/VOLCENGINE_TTS_ACCESS_KEY"
            )

        connect_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        async with websocket_connect(
            self.settings.volcengine_tts_base_url,
            additional_headers=self._request_headers(connect_id),
            open_timeout=self.settings.volcengine_api_timeout_seconds,
            close_timeout=2,
        ) as websocket:
            await websocket.send(_volcengine_client_frame(VolcengineEventSend.START_CONNECTION))
            await self._wait_for_event(
                websocket,
                request_id=connect_id,
                expected={VolcengineEventReceive.CONNECTION_STARTED},
            )

            start_payload = self._start_session_payload(language)
            await websocket.send(
                _volcengine_client_frame(
                    VolcengineEventSend.START_SESSION,
                    session_id=session_id,
                    payload=start_payload,
                )
            )
            await self._wait_for_event(
                websocket,
                request_id=connect_id,
                expected={VolcengineEventReceive.SESSION_STARTED},
            )

            await websocket.send(
                _volcengine_client_frame(
                    VolcengineEventSend.TASK_REQUEST,
                    session_id=session_id,
                    payload=self._task_request_payload(clean, language),
                )
            )
            await websocket.send(
                _volcengine_client_frame(
                    VolcengineEventSend.FINISH_SESSION,
                    session_id=session_id,
                    payload={},
                )
            )

            async for raw_message in websocket:
                if not isinstance(raw_message, bytes):
                    continue
                response = parse_volcengine_tts_response(raw_message)
                if (
                    response.event == VolcengineEventReceive.TTS_RESPONSE
                    and isinstance(response.payload, bytes)
                    and response.payload
                ):
                    yield volcengine_audio_bytes_to_pcm(
                        response.payload,
                        encoding=self.settings.volcengine_tts_encoding,
                        sample_rate=sample_rate,
                    )
                elif response.event in {
                    VolcengineEventReceive.SESSION_FINISHED,
                    VolcengineEventReceive.TTS_ENDED,
                }:
                    break
                elif _is_volcengine_error_event(response.event) or response.event in {
                    VolcengineEventReceive.CONNECTION_FAILED,
                    VolcengineEventReceive.SESSION_FAILED,
                    VolcengineEventReceive.SERVER_PROCESSING_ERROR,
                }:
                    raise TtsProviderError(
                        f"Volcengine TTS failed ({connect_id}): {response.payload!r}"
                    )

            await websocket.send(_volcengine_client_frame(VolcengineEventSend.FINISH_CONNECTION))

    async def _wait_for_event(
        self,
        websocket: Any,
        *,
        request_id: str,
        expected: set[VolcengineEventReceive],
    ) -> None:
        while True:
            raw_message = await websocket.recv()
            if not isinstance(raw_message, bytes):
                continue
            response = parse_volcengine_tts_response(raw_message)
            if response.event in expected:
                return
            if _is_volcengine_error_event(response.event) or response.event in {
                VolcengineEventReceive.CONNECTION_FAILED,
                VolcengineEventReceive.SESSION_FAILED,
                VolcengineEventReceive.SERVER_PROCESSING_ERROR,
            }:
                raise TtsProviderError(
                    f"Volcengine TTS failed ({request_id}): {response.payload!r}"
                )

    def _request_headers(self, connect_id: str | None = None) -> dict[str, str]:
        headers = {
            "X-Api-Resource-Id": self.settings.volcengine_tts_resource_id,
            "X-Api-Connect-Id": connect_id or uuid.uuid4().hex,
        }
        if self.settings.volcengine_tts_api_key:
            headers["X-Api-Key"] = self.settings.volcengine_tts_api_key
        elif self.settings.volcengine_tts_app_id and self.settings.volcengine_tts_access_key:
            headers["X-Api-App-Id"] = self.settings.volcengine_tts_app_id
            headers["X-Api-Access-Key"] = self.settings.volcengine_tts_access_key
        return headers

    def _request_payload(self, text: str, language: str | None) -> dict[str, Any]:
        return self._task_request_payload(text, language)

    def _start_session_payload(self, language: str | None) -> dict[str, Any]:
        return {
            "event": VolcengineEventSend.START_SESSION.value,
            "namespace": "BidirectionalTTS",
            "user": {"uid": "asuka-realtime"},
            "req_params": self._session_req_params(),
        }

    def _task_request_payload(self, text: str, language: str | None) -> dict[str, Any]:
        return {
            "event": VolcengineEventSend.TASK_REQUEST.value,
            "namespace": "BidirectionalTTS",
            "user": {"uid": "asuka-realtime"},
            "req_params": self._task_req_params(text, language),
        }

    def _session_req_params(self) -> dict[str, Any]:
        return {
            "speaker": self.settings.volcengine_tts_voice_type,
            "audio_params": {
                "format": self.settings.volcengine_tts_encoding,
                "sample_rate": self.settings.volcengine_tts_sample_rate,
            },
        }

    def _task_req_params(self, text: str, language: str | None) -> dict[str, Any]:
        additions: dict[str, Any] = {}
        explicit_language = _volcengine_explicit_language(language)
        if explicit_language:
            additions["explicit_language"] = explicit_language

        req_params: dict[str, Any] = {"text": text}
        if additions:
            req_params["additions"] = additions
        return req_params

    def _legacy_http_payload(self, text: str, language: str | None) -> dict[str, Any]:
        req_params = self._session_req_params() | self._task_req_params(text, language)
        return {
            "user": {"uid": "asuka-realtime"},
            "req_params": req_params,
        }

    def _clean(self, text: str) -> str:
        return URL_RE.sub(" ", clean_text_for_speech(text)).strip()

    def open_stream(self) -> "VolcengineTtsConnection":
        """Open a persistent connection reused across a voice session's sentences."""
        return VolcengineTtsConnection(self)


class VolcengineTtsConnection:
    """A persistent Volcengine bidirectional TTS connection.

    One WebSocket hosts one session per sentence, so every sentence after the
    first skips the connection handshake (the main source of inter-sentence
    gaps). A single connection cannot multiplex sessions, so access is
    serialized by an internal lock. If a session is interrupted before
    ``SESSION_FINISHED`` (e.g. the turn is cancelled) the connection is dropped
    and transparently re-established on the next sentence.
    """

    def __init__(self, provider: VolcengineTtsProvider) -> None:
        self._provider = provider
        self.settings = provider.settings
        self._ws: Any | None = None
        self._connect_id: str | None = None
        self._lock = asyncio.Lock()

    async def render(self, text: str, *, language: str | None) -> SynthesizedPcm:
        sample_rate = self.settings.volcengine_tts_sample_rate
        clean = self._provider._clean(text)
        if not clean:
            return SynthesizedPcm(pcm=b"", sample_rate=sample_rate)

        async with self._lock:
            completed = False
            try:
                await self._ensure_connected()
                ws = self._ws
                assert ws is not None
                session_id = uuid.uuid4().hex
                await ws.send(
                    _volcengine_client_frame(
                        VolcengineEventSend.START_SESSION,
                        session_id=session_id,
                        payload=self._provider._start_session_payload(language),
                    )
                )
                await self._provider._wait_for_event(
                    ws,
                    request_id=self._connect_id or "",
                    expected={VolcengineEventReceive.SESSION_STARTED},
                )
                await ws.send(
                    _volcengine_client_frame(
                        VolcengineEventSend.TASK_REQUEST,
                        session_id=session_id,
                        payload=self._provider._task_request_payload(clean, language),
                    )
                )
                await ws.send(
                    _volcengine_client_frame(
                        VolcengineEventSend.FINISH_SESSION,
                        session_id=session_id,
                        payload={},
                    )
                )

                chunks = bytearray()
                async for raw_message in ws:
                    if not isinstance(raw_message, bytes):
                        continue
                    response = parse_volcengine_tts_response(raw_message)
                    if (
                        response.event == VolcengineEventReceive.TTS_RESPONSE
                        and isinstance(response.payload, bytes)
                        and response.payload
                    ):
                        audio = volcengine_audio_bytes_to_pcm(
                            response.payload,
                            encoding=self.settings.volcengine_tts_encoding,
                            sample_rate=sample_rate,
                        )
                        chunks.extend(audio.pcm)
                        sample_rate = audio.sample_rate
                    elif response.event == VolcengineEventReceive.SESSION_FINISHED:
                        completed = True
                        break
                    elif response.event == VolcengineEventReceive.TTS_ENDED:
                        # Audio is done; keep reading until SESSION_FINISHED so the
                        # connection is left clean for the next sentence.
                        continue
                    elif _is_volcengine_error_event(response.event) or response.event in {
                        VolcengineEventReceive.CONNECTION_FAILED,
                        VolcengineEventReceive.SESSION_FAILED,
                        VolcengineEventReceive.SERVER_PROCESSING_ERROR,
                    }:
                        raise TtsProviderError(
                            f"Volcengine TTS failed ({self._connect_id}): {response.payload!r}"
                        )

                return SynthesizedPcm(pcm=bytes(chunks), sample_rate=sample_rate)
            finally:
                # An incomplete session leaves unread frames on the wire, so the
                # connection can only be safely reused after a clean finish.
                if not completed:
                    await self._drop()

    async def _ensure_connected(self) -> None:
        if self._ws is not None:
            return
        if not (
            self.settings.volcengine_tts_api_key
            or (self.settings.volcengine_tts_app_id and self.settings.volcengine_tts_access_key)
        ):
            raise TtsProviderError(
                "missing VOLCENGINE_TTS_API_KEY or "
                "VOLCENGINE_TTS_APP_ID/VOLCENGINE_TTS_ACCESS_KEY"
            )

        connect_id = uuid.uuid4().hex
        ws = await websocket_connect(
            self.settings.volcengine_tts_base_url,
            additional_headers=self._provider._request_headers(connect_id),
            open_timeout=self.settings.volcengine_api_timeout_seconds,
            close_timeout=2,
        )
        try:
            await ws.send(_volcengine_client_frame(VolcengineEventSend.START_CONNECTION))
            await self._provider._wait_for_event(
                ws,
                request_id=connect_id,
                expected={VolcengineEventReceive.CONNECTION_STARTED},
            )
        except BaseException:
            await ws.close()
            raise
        self._ws = ws
        self._connect_id = connect_id

    async def _drop(self) -> None:
        ws, self._ws, self._connect_id = self._ws, None, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def aclose(self) -> None:
        async with self._lock:
            ws, self._ws, self._connect_id = self._ws, None, None
            if ws is None:
                return
            try:
                await ws.send(_volcengine_client_frame(VolcengineEventSend.FINISH_CONNECTION))
            except Exception:  # noqa: BLE001
                pass
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass


@dataclass(frozen=True)
class VolcengineTtsResponse:
    """Parsed Volcengine bidirectional TTS WebSocket response."""

    event: VolcengineEventReceive | int
    session_id: str
    payload: bytes | dict[str, Any]


def _volcengine_client_frame(
    event: VolcengineEventSend,
    *,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bytes:
    payload_bytes = json.dumps(payload or {}, ensure_ascii=False).encode()
    frame = bytearray(
        [
            0x11,
            (VolcengineMessageType.FULL_CLIENT_REQUEST.value << 4) | 0b0100,
            (VolcengineSerializationMethod.JSON.value << 4),
            0x00,
        ]
    )
    frame.extend(struct.pack(">I", event.value))
    if session_id is not None:
        session_bytes = session_id.encode()
        frame.extend(struct.pack(">I", len(session_bytes)))
        frame.extend(session_bytes)
    frame.extend(struct.pack(">I", len(payload_bytes)))
    frame.extend(payload_bytes)
    return bytes(frame)


def parse_volcengine_tts_response(data: bytes) -> VolcengineTtsResponse:
    """Parse a Volcengine bidirectional TTS WebSocket response frame."""
    if len(data) < 8:
        raise TtsProviderError("Volcengine TTS response frame is too short")

    message_type = VolcengineMessageType((data[1] >> 4) & 0b1111)
    serialization_method = VolcengineSerializationMethod((data[2] >> 4) & 0b1111)
    event_number = struct.unpack(">I", data[4:8])[0]
    try:
        event: VolcengineEventReceive | int = VolcengineEventReceive(event_number)
    except ValueError:
        event = event_number

    offset = 8
    session_id = ""
    if len(data) >= offset + 4:
        session_length = struct.unpack(">I", data[offset : offset + 4])[0]
        session_start = offset + 4
        session_end = session_start + session_length
        if session_length <= len(data) - session_start:
            try:
                session_id = data[session_start:session_end].decode()
                offset = session_end
            except UnicodeDecodeError:
                session_id = ""

    payload = data[offset + 4 :] if len(data) >= offset + 4 else b""
    if len(data) >= offset + 4:
        payload_length = struct.unpack(">I", data[offset : offset + 4])[0]
        payload_end = offset + 4 + payload_length
        if payload_length <= len(data) - offset - 4:
            payload = data[offset + 4 : payload_end]

    if message_type == VolcengineMessageType.ERROR_INFORMATION:
        decoded_error = _decode_volcengine_json_payload(payload)
        return VolcengineTtsResponse(event=event, session_id=session_id, payload=decoded_error)

    if serialization_method == VolcengineSerializationMethod.JSON:
        decoded = _decode_volcengine_json_payload(payload)
        if event == VolcengineEventReceive.TTS_RESPONSE:
            audio = _audio_bytes_from_volcengine_json(decoded, allow_empty=True)
            return VolcengineTtsResponse(event=event, session_id=session_id, payload=audio)
        return VolcengineTtsResponse(event=event, session_id=session_id, payload=decoded)

    return VolcengineTtsResponse(event=event, session_id=session_id, payload=payload)


def _decode_volcengine_json_payload(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload.decode())
    except json.JSONDecodeError as exc:
        raise TtsProviderError(f"Volcengine TTS response payload is not JSON: {payload!r}") from exc
    if not isinstance(decoded, dict):
        raise TtsProviderError(f"Volcengine TTS response JSON is not an object: {decoded!r}")
    return decoded


def _volcengine_explicit_language(language: str | None) -> str | None:
    normalized = normalize_language(language)
    return {
        "english": "en",
        "japanese": "ja",
        "korean": "ko",
    }.get(normalized)


def _is_volcengine_error_event(event: VolcengineEventReceive | int) -> bool:
    return isinstance(event, int) and event >= 40_000_000


def wav_bytes_to_pcm(audio_bytes: bytes) -> SynthesizedPcm:
    """Decode WAV bytes into mono s16 PCM."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except wave.Error as exc:
        raise TtsProviderError("Qwen3-TTS audio is not a supported WAV payload") from exc

    if sample_width == 2:
        samples = np.frombuffer(frames, dtype=np.int16)
    elif sample_width == 1:
        u8 = np.frombuffer(frames, dtype=np.uint8).astype(np.int16)
        samples = (u8 - 128) << 8
    elif sample_width == 4:
        f32 = np.frombuffer(frames, dtype=np.float32)
        samples = np.clip(f32, -1.0, 1.0)
        samples = (samples * 32767.0).astype(np.int16)
    else:
        raise TtsProviderError(f"unsupported Qwen3-TTS WAV sample width: {sample_width}")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

    return SynthesizedPcm(pcm=samples.astype(np.int16).tobytes(), sample_rate=sample_rate)


def volcengine_audio_bytes_to_pcm(
    audio_bytes: bytes,
    *,
    encoding: str,
    sample_rate: int,
) -> SynthesizedPcm:
    """Decode Volcengine audio bytes into mono s16 PCM."""
    normalized = encoding.lower()
    if normalized == "wav":
        return wav_bytes_to_pcm(audio_bytes)
    if normalized in {"pcm", "raw", "s16le"}:
        return SynthesizedPcm(pcm=audio_bytes, sample_rate=sample_rate)
    raise TtsProviderError(f"unsupported Volcengine TTS encoding: {encoding}")


def compressed_audio_bytes_to_pcm(
    audio_bytes: bytes,
    *,
    target_sample_rate: int,
) -> SynthesizedPcm:
    """Decode compressed audio bytes into mono s16 PCM."""
    if not audio_bytes:
        return SynthesizedPcm(pcm=b"", sample_rate=target_sample_rate)
    if audio_bytes.startswith(b"RIFF"):
        return wav_bytes_to_pcm(audio_bytes)

    output = bytearray()
    try:
        with av.open(io.BytesIO(audio_bytes)) as opened:
            container = opened
            if not isinstance(container, InputContainer):
                raise TtsProviderError("compressed TTS audio is not an input container")
            resampler = AudioResampler(
                format="s16",
                layout="mono",
                rate=target_sample_rate,
            )
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    output.extend(bytes(converted.planes[0]))
            for converted in resampler.resample(None):
                output.extend(bytes(converted.planes[0]))
    except FFmpegError as exc:
        raise TtsProviderError("compressed TTS audio could not be decoded") from exc

    if not output:
        raise TtsProviderError("compressed TTS audio decoded to empty PCM")
    return SynthesizedPcm(pcm=bytes(output), sample_rate=target_sample_rate)


def decode_volcengine_audio_chunks(body: bytes) -> bytes:
    """Extract concatenated audio bytes from a Volcengine TTS response body."""
    stripped = body.strip()
    if not stripped:
        raise TtsProviderError("Volcengine TTS response body is empty")

    if stripped.startswith(b"{") and b"\n" not in stripped:
        return _audio_bytes_from_volcengine_json(json.loads(stripped.decode("utf-8")))

    audio = bytearray()
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(b"data:"):
            line = line[5:].strip()
        if line in {b"[DONE]", b"done"}:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        audio.extend(_audio_bytes_from_volcengine_json(payload, allow_empty=True))

    if not audio:
        raise TtsProviderError("Volcengine TTS response has no audio data")
    return bytes(audio)


def _audio_bytes_from_volcengine_json(
    payload: dict[str, Any],
    *,
    allow_empty: bool = False,
) -> bytes:
    if _volcengine_error_code(payload):
        raise TtsProviderError(f"Volcengine TTS error response: {payload}")

    candidates: list[Any] = [
        payload.get("data"),
        payload.get("audio"),
        payload.get("payload"),
    ]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("data"), result.get("audio"), result.get("payload")])

    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return base64.b64decode(candidate)
        if isinstance(candidate, dict):
            for key in ("data", "audio", "payload"):
                value = candidate.get(key)
                if isinstance(value, str) and value:
                    return base64.b64decode(value)

    if allow_empty:
        return b""
    raise TtsProviderError("Volcengine TTS response missing base64 audio data")


def _volcengine_error_code(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    if code in (None, 0, "0", 200, "200", 20_000_000, "20000000"):
        return False
    return True


_tts_provider: RealtimeTtsProvider | None = None


def get_tts_provider() -> RealtimeTtsProvider:
    """Return the process-wide realtime TTS provider."""
    global _tts_provider
    if _tts_provider is None:
        provider = get_settings().realtime_tts_provider.lower()
        if provider in {"qwen", "qwen3", "qwen3tts", "qwen3-tts"}:
            _tts_provider = Qwen3TtsProvider()
        elif provider in {"edge", "edge_tts", "edgetts", "edge-tts"}:
            _tts_provider = EdgeTtsProvider()
        elif provider in {"volc", "volcano", "volcengine", "doubao"}:
            _tts_provider = VolcengineTtsProvider()
        elif provider == "piper":
            _tts_provider = PiperTtsProvider()
        else:
            raise TtsProviderError(f"unsupported realtime TTS provider: {provider}")
    return _tts_provider


def set_tts_provider(provider: RealtimeTtsProvider | None) -> None:
    """Override the process-wide TTS provider for tests."""
    global _tts_provider
    _tts_provider = provider
