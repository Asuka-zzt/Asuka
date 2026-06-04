"""Realtime TTS provider tests."""

import io
import struct
import wave
from typing import Any

import pytest

from asuka.config import Settings
from asuka.core.voice import tts
from asuka.core.voice.tts import (
    EdgeTtsProvider,
    Qwen3TtsProvider,
    SynthesizedPcm,
    VolcengineEventReceive,
    VolcengineEventSend,
    VolcengineMessageType,
    VolcengineSerializationMethod,
    VolcengineTtsProvider,
    VolcengineTtsResponse,
    compressed_audio_bytes_to_pcm,
    decode_volcengine_audio_chunks,
    parse_volcengine_tts_response,
    sentence_segments,
    volcengine_audio_bytes_to_pcm,
    wav_bytes_to_pcm,
)


def make_wav_bytes(
    pcm: bytes,
    *,
    sample_rate: int = 24_000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def make_volcengine_server_frame(
    event: VolcengineEventReceive,
    payload: bytes | dict[str, Any] = b"",
    *,
    session_id: str = "session-test",
    serialization: VolcengineSerializationMethod = VolcengineSerializationMethod.RAW,
) -> bytes:
    payload_bytes = (
        payload
        if isinstance(payload, bytes)
        else __import__("json").dumps(payload, ensure_ascii=False).encode()
    )
    session_bytes = session_id.encode()
    return b"".join(
        [
            bytes(
                [
                    0x11,
                    (VolcengineMessageType.FULL_SERVER_RESPONSE.value << 4) | 0b0100,
                    (serialization.value << 4),
                    0,
                ]
            ),
            struct.pack(">I", event.value),
            struct.pack(">I", len(session_bytes)),
            session_bytes,
            struct.pack(">I", len(payload_bytes)),
            payload_bytes,
        ]
    )


def test_wav_bytes_to_pcm_decodes_mono_s16() -> None:
    audio = wav_bytes_to_pcm(make_wav_bytes(b"\x20\x00" * 8, sample_rate=24_000))

    assert audio == SynthesizedPcm(pcm=b"\x20\x00" * 8, sample_rate=24_000)


def test_wav_bytes_to_pcm_downmixes_stereo() -> None:
    left = (1000).to_bytes(2, "little", signed=True)
    right = (3000).to_bytes(2, "little", signed=True)
    audio = wav_bytes_to_pcm(make_wav_bytes((left + right) * 4, channels=2))

    assert audio.sample_rate == 24_000
    assert audio.pcm == (2000).to_bytes(2, "little", signed=True) * 4


def test_qwen3_payload_maps_language_type() -> None:
    provider = Qwen3TtsProvider(
        Settings(
            dashscope_api_key="test-key",
            qwen_tts_voice="Cherry",
        )
    )

    payload = provider._request_payload("你好", "japanese")

    assert payload["model"] == "qwen3-tts-flash"
    assert payload["input"] == {"text": "你好"}
    assert payload["parameters"]["voice"] == "Cherry"
    assert payload["parameters"]["language_type"] == "Japanese"


def test_get_tts_provider_selects_qwen3(monkeypatch: pytest.MonkeyPatch) -> None:
    tts.set_tts_provider(None)
    monkeypatch.setattr(
        "asuka.core.voice.tts.get_settings",
        lambda: Settings(realtime_tts_provider="qwen3", dashscope_api_key="test-key"),
    )

    provider = tts.get_tts_provider()

    assert isinstance(provider, Qwen3TtsProvider)
    tts.set_tts_provider(None)


def test_compressed_audio_bytes_to_pcm_decodes_audio_container() -> None:
    wav_bytes = make_wav_bytes(b"\x20\x00" * 4, sample_rate=24_000)

    audio = compressed_audio_bytes_to_pcm(wav_bytes, target_sample_rate=48_000)

    assert audio.sample_rate == 24_000
    assert audio.pcm


@pytest.mark.asyncio
async def test_edge_tts_provider_decodes_existing_tts_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_synthesize_speech(
        text: str,
        voice: str | None = None,
        language: str | None = None,
    ) -> bytes:
        assert text == "你好"
        assert voice is None
        assert language == "chinese"
        return make_wav_bytes(b"\x20\x00" * 4, sample_rate=24_000)

    monkeypatch.setattr(
        "asuka.api.provider.tts.synthesize_speech",
        fake_synthesize_speech,
    )
    provider = EdgeTtsProvider(Settings(piper_sample_rate=48_000))

    audio = await provider.synthesize("你好", language="chinese")

    assert audio.sample_rate == 24_000
    assert audio.pcm


def test_get_tts_provider_selects_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    tts.set_tts_provider(None)
    monkeypatch.setattr(
        "asuka.core.voice.tts.get_settings",
        lambda: Settings(realtime_tts_provider="edge"),
    )

    provider = tts.get_tts_provider()

    assert isinstance(provider, EdgeTtsProvider)
    tts.set_tts_provider(None)


def test_volcengine_payloads_and_api_key_headers_use_new_console_schema() -> None:
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_app_id="",
            volcengine_tts_access_key="",
            volcengine_tts_voice_type="zh_female_test",
            volcengine_tts_encoding="pcm",
            volcengine_tts_sample_rate=24_000,
        )
    )

    start_payload = provider._start_session_payload("chinese")
    task_payload = provider._request_payload("你好", "chinese")
    headers = provider._request_headers()

    assert start_payload["event"] == VolcengineEventSend.START_SESSION.value
    assert start_payload["namespace"] == "BidirectionalTTS"
    assert start_payload["user"] == {"uid": "asuka-realtime"}
    assert start_payload["req_params"] == {
        "speaker": "zh_female_test",
        "audio_params": {
            "format": "pcm",
            "sample_rate": 24_000,
        },
    }
    assert "text" not in start_payload["req_params"]

    assert task_payload["event"] == VolcengineEventSend.TASK_REQUEST.value
    assert task_payload["namespace"] == "BidirectionalTTS"
    assert task_payload["user"] == {"uid": "asuka-realtime"}
    assert task_payload["req_params"] == {"text": "你好"}
    assert "speaker" not in task_payload["req_params"]
    assert "audio_params" not in task_payload["req_params"]

    assert provider.settings.volcengine_tts_resource_id == "seed-tts-2.0"
    assert headers["X-Api-Key"] == "test-api-key"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert "X-Api-Connect-Id" in headers
    assert "X-Api-Request-Id" not in headers


def test_volcengine_legacy_http_payload_keeps_text_and_audio_config() -> None:
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_voice_type="zh_female_test",
            volcengine_tts_encoding="pcm",
            volcengine_tts_sample_rate=24_000,
        )
    )

    payload = provider._legacy_http_payload("你好", "chinese")

    assert payload["user"] == {"uid": "asuka-realtime"}
    assert payload["req_params"] == {
        "text": "你好",
        "speaker": "zh_female_test",
        "audio_params": {
            "format": "pcm",
            "sample_rate": 24_000,
        },
    }


def test_volcengine_defaults_to_bidirectional_websocket_pcm() -> None:
    provider = VolcengineTtsProvider(
        Settings(_env_file=None, volcengine_tts_api_key="test-api-key")
    )

    assert provider.settings.volcengine_tts_base_url.endswith("/api/v3/tts/bidirection")
    assert provider.settings.volcengine_tts_encoding == "pcm"
    assert provider.settings.volcengine_tts_resource_id == "seed-tts-2.0"


def test_volcengine_headers_support_legacy_app_auth() -> None:
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="",
            volcengine_tts_app_id="app-id",
            volcengine_tts_access_key="access-key",
        )
    )

    headers = provider._request_headers()

    assert headers["X-Api-App-Id"] == "app-id"
    assert headers["X-Api-Access-Key"] == "access-key"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert "X-Api-Connect-Id" in headers
    assert "X-Api-App-Key" not in headers
    assert "X-Api-Key" not in headers


def test_volcengine_api_key_takes_precedence_over_legacy_app_auth() -> None:
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_app_id="app-id",
            volcengine_tts_access_key="access-key",
        )
    )

    headers = provider._request_headers()

    assert headers["X-Api-Key"] == "test-api-key"
    assert "X-Api-App-Id" not in headers
    assert "X-Api-Access-Key" not in headers


def test_volcengine_session_payload_omits_task_language_additions() -> None:
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_voice_type="zh_female_test",
            volcengine_tts_encoding="pcm",
            volcengine_tts_sample_rate=24_000,
        )
    )

    payload = provider._start_session_payload("japanese")

    assert payload["req_params"] == {
        "speaker": "zh_female_test",
        "audio_params": {
            "format": "pcm",
            "sample_rate": 24_000,
        },
    }


def test_volcengine_task_payload_uses_text_only_schema_for_unmapped_language() -> None:
    provider = VolcengineTtsProvider(Settings(volcengine_tts_api_key="test-api-key"))

    payload = provider._task_request_payload("Hello", "spanish")

    assert payload["req_params"] == {"text": "Hello"}


def test_volcengine_task_payload_maps_explicit_language() -> None:
    provider = VolcengineTtsProvider(Settings(volcengine_tts_api_key="test-api-key"))

    payload = provider._task_request_payload("こんにちは", "japanese")

    assert payload["req_params"] == {
        "text": "こんにちは",
        "additions": {"explicit_language": "ja"},
    }


def test_decode_volcengine_audio_chunks_from_single_json() -> None:
    body = b'{"code":0,"data":"IAAgAA=="}'

    audio = decode_volcengine_audio_chunks(body)

    assert audio == b"\x20\x00\x20\x00"


def test_decode_volcengine_audio_chunks_from_sse_lines() -> None:
    body = b'data: {"code":0,"data":"IAA="}\n\ndata: {"code":0,"data":"QA0="}\n'

    audio = decode_volcengine_audio_chunks(body)

    assert audio == b"\x20\x00\x40\x0d"


def test_decode_volcengine_audio_chunks_from_json_lines() -> None:
    body = b'{"code":0,"data":"IAA="}\n{"code":0,"data":"QA0="}\n'

    audio = decode_volcengine_audio_chunks(body)

    assert audio == b"\x20\x00\x40\x0d"


def test_decode_volcengine_audio_chunks_accepts_v3_success_code() -> None:
    body = b'{"code":20000000,"message":"OK","data":null}\n{"code":20000000,"data":"IAA="}\n'

    audio = decode_volcengine_audio_chunks(body)

    assert audio == b"\x20\x00"


def test_volcengine_audio_bytes_to_pcm_supports_raw_pcm() -> None:
    audio = volcengine_audio_bytes_to_pcm(
        b"\x20\x00" * 4,
        encoding="pcm",
        sample_rate=24_000,
    )

    assert audio == SynthesizedPcm(pcm=b"\x20\x00" * 4, sample_rate=24_000)


def test_volcengine_audio_bytes_to_pcm_supports_wav() -> None:
    wav_bytes = make_wav_bytes(b"\x20\x00" * 4, sample_rate=24_000)

    audio = volcengine_audio_bytes_to_pcm(wav_bytes, encoding="wav", sample_rate=16_000)

    assert audio == SynthesizedPcm(pcm=b"\x20\x00" * 4, sample_rate=24_000)


def test_parse_volcengine_tts_raw_audio_response() -> None:
    response = parse_volcengine_tts_response(
        make_volcengine_server_frame(
            VolcengineEventReceive.TTS_RESPONSE,
            b"\x20\x00\x40\x00",
        )
    )

    assert response == VolcengineTtsResponse(
        event=VolcengineEventReceive.TTS_RESPONSE,
        session_id="session-test",
        payload=b"\x20\x00\x40\x00",
    )


@pytest.mark.asyncio
async def test_volcengine_stream_synthesize_yields_websocket_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[bytes] = []

    class FakeWebSocket:
        def __init__(self) -> None:
            self.recv_messages = [
                make_volcengine_server_frame(VolcengineEventReceive.CONNECTION_STARTED),
                make_volcengine_server_frame(VolcengineEventReceive.SESSION_STARTED),
            ]
            self.stream_messages = [
                make_volcengine_server_frame(
                    VolcengineEventReceive.TTS_RESPONSE,
                    b"\x20\x00",
                ),
                make_volcengine_server_frame(
                    VolcengineEventReceive.TTS_RESPONSE,
                    b"\x40\x00",
                ),
                make_volcengine_server_frame(VolcengineEventReceive.SESSION_FINISHED),
            ]

        async def send(self, message: bytes) -> None:
            sent_messages.append(message)

        async def recv(self) -> bytes:
            return self.recv_messages.pop(0)

        def __aiter__(self) -> "FakeWebSocket":
            return self

        async def __anext__(self) -> bytes:
            if not self.stream_messages:
                raise StopAsyncIteration
            return self.stream_messages.pop(0)

    class FakeConnect:
        async def __aenter__(self) -> FakeWebSocket:
            return FakeWebSocket()

        async def __aexit__(self, *_args: object) -> None:
            return None

    def fake_connect(*_args: object, **_kwargs: object) -> FakeConnect:
        return FakeConnect()

    monkeypatch.setattr("asuka.core.voice.tts.websocket_connect", fake_connect)
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_encoding="pcm",
            volcengine_tts_sample_rate=24_000,
        )
    )

    chunks = [chunk async for chunk in provider.stream_synthesize("你好", language="chinese")]

    assert chunks == [
        SynthesizedPcm(pcm=b"\x20\x00", sample_rate=24_000),
        SynthesizedPcm(pcm=b"\x40\x00", sample_rate=24_000),
    ]
    assert len(sent_messages) == 5


@pytest.mark.asyncio
async def test_volcengine_connection_reuses_one_websocket_across_sentences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect_calls = 0

    class FakeWebSocket:
        def __init__(self) -> None:
            self.queue: list[bytes] = [
                make_volcengine_server_frame(VolcengineEventReceive.CONNECTION_STARTED),
            ]
            self.closed = False

        def _queue_session(self, audio: bytes) -> None:
            self.queue += [
                make_volcengine_server_frame(VolcengineEventReceive.SESSION_STARTED),
                make_volcengine_server_frame(VolcengineEventReceive.TTS_RESPONSE, audio),
                make_volcengine_server_frame(VolcengineEventReceive.SESSION_FINISHED),
            ]

        async def send(self, message: bytes) -> None:
            return None

        async def recv(self) -> bytes:
            return self.queue.pop(0)

        def __aiter__(self) -> "FakeWebSocket":
            return self

        async def __anext__(self) -> bytes:
            if not self.queue:
                raise StopAsyncIteration
            return self.queue.pop(0)

        async def close(self) -> None:
            self.closed = True

    ws = FakeWebSocket()

    async def fake_connect(*_args: object, **_kwargs: object) -> FakeWebSocket:
        nonlocal connect_calls
        connect_calls += 1
        return ws

    monkeypatch.setattr("asuka.core.voice.tts.websocket_connect", fake_connect)
    provider = VolcengineTtsProvider(
        Settings(
            volcengine_tts_api_key="test-api-key",
            volcengine_tts_encoding="pcm",
            volcengine_tts_sample_rate=24_000,
        )
    )
    connection = provider.open_stream()

    ws._queue_session(b"\x20\x00")
    first = await connection.render("第一句。", language="chinese")
    ws._queue_session(b"\x40\x00")
    second = await connection.render("第二句。", language="chinese")

    assert first == SynthesizedPcm(pcm=b"\x20\x00", sample_rate=24_000)
    assert second == SynthesizedPcm(pcm=b"\x40\x00", sample_rate=24_000)
    assert connect_calls == 1  # one handshake reused for both sentences
    assert not ws.closed

    await connection.aclose()
    assert ws.closed


def test_sentence_segments_can_eagerly_split_for_streaming_tts() -> None:
    segments, remaining = sentence_segments("你好，我正在准备回答", eager=True)

    assert segments == ["你好，"]
    assert remaining == "我正在准备回答"


def test_get_tts_provider_selects_volcengine(monkeypatch: pytest.MonkeyPatch) -> None:
    tts.set_tts_provider(None)
    monkeypatch.setattr(
        "asuka.core.voice.tts.get_settings",
        lambda: Settings(
            realtime_tts_provider="volcengine",
            volcengine_tts_api_key="test-api-key",
        ),
    )

    provider = tts.get_tts_provider()

    assert isinstance(provider, VolcengineTtsProvider)
    tts.set_tts_provider(None)
