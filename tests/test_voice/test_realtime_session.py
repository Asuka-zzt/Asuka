"""Realtime voice session event handling."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from asuka.core.agent.model import AgentConfig
from asuka.core.voice.session import RealtimeVoiceSession
from asuka.core.voice.tts import SynthesizedPcm


class FakeDataChannel:
    """Minimal RTCDataChannel test double."""

    readyState = "open"

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send(self, message: str) -> None:
        self.messages.append(json.loads(message))


class FakeAgent:
    """Agent that emits one text chunk and finishes."""

    async def astream_events(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> Any:
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="你好[emotion:happy]")},
        }


class FakeMultiSentenceAgent:
    """Agent that emits two complete spoken sentences in one stream chunk."""

    async def astream_events(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> Any:
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="第一句。第二句。")},
        }


class FakeAsr:
    async def transcribe(self, *_args: Any, **_kwargs: Any) -> str:
        return "后端转写"


class FakeTts:
    async def synthesize(self, text: str, **_kwargs: Any) -> SynthesizedPcm:
        return SynthesizedPcm(pcm=(b"\x20\x00" * max(1, len(text) * 100)), sample_rate=48_000)


class SlowFirstSentenceTts:
    async def synthesize(self, text: str, **_kwargs: Any) -> SynthesizedPcm:
        if text.startswith("第一句"):
            await asyncio.sleep(0.02)
        return SynthesizedPcm(pcm=text.encode(), sample_rate=48_000)


class StreamingTts:
    async def synthesize(self, text: str, **_kwargs: Any) -> SynthesizedPcm:
        return SynthesizedPcm(pcm=text.encode(), sample_rate=48_000)

    async def stream_synthesize(self, text: str, **_kwargs: Any) -> Any:
        yield SynthesizedPcm(pcm=f"{text}:a".encode(), sample_rate=48_000)
        await asyncio.sleep(0)
        yield SynthesizedPcm(pcm=f"{text}:b".encode(), sample_rate=48_000)


@pytest.mark.asyncio
async def test_text_send_streams_realtime_events(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_build_agent(_config: AgentConfig) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("asuka.core.voice.session.build_agent", fake_build_agent)
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=FakeTts(),
    )
    channel = FakeDataChannel()
    session.data_channel = channel

    await session.handle_data_message(
        json.dumps({"type": "text.send", "payload": {"content": "早上好"}})
    )
    assert session._active_task is not None
    await session._active_task
    if session._tts_tasks:
        await asyncio.gather(*session._tts_tasks)

    event_types = [message["type"] for message in channel.messages]
    assert "input.transcript.final" in event_types
    assert "live2d.emotion" in event_types
    assert "chat.token" in event_types
    assert "voice.speech_start" in event_types
    assert "voice.speech_end" in event_types
    assert "done" in event_types
    assert channel.messages[0]["payload"] == {"text": "早上好"}
    assert any(message["payload"] == {"emotion": "happy"} for message in channel.messages)
    assert any(message["payload"] == {"content": "你好"} for message in channel.messages)


@pytest.mark.asyncio
async def test_tts_audio_is_enqueued_in_sentence_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_build_agent(_config: AgentConfig) -> FakeMultiSentenceAgent:
        return FakeMultiSentenceAgent()

    monkeypatch.setattr("asuka.core.voice.session.build_agent", fake_build_agent)
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=SlowFirstSentenceTts(),
    )
    session.data_channel = FakeDataChannel()

    await session.handle_data_message(
        json.dumps({"type": "text.send", "payload": {"content": "开始"}})
    )
    assert session._active_task is not None
    await session._active_task
    if session._tts_tasks:
        await asyncio.gather(*session._tts_tasks)

    first = session.outbound_audio._queue.get_nowait()
    second = session.outbound_audio._queue.get_nowait()

    assert first == "第一句。".encode()
    assert second == "第二句。".encode()


@pytest.mark.asyncio
async def test_streaming_tts_chunks_are_enqueued_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_build_agent(_config: AgentConfig) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("asuka.core.voice.session.build_agent", fake_build_agent)
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=StreamingTts(),
    )
    channel = FakeDataChannel()
    session.data_channel = channel

    await session.handle_data_message(
        json.dumps({"type": "text.send", "payload": {"content": "开始"}})
    )
    assert session._active_task is not None
    await session._active_task
    if session._tts_tasks:
        await asyncio.gather(*session._tts_tasks)

    first = session.outbound_audio._queue.get_nowait()
    second = session.outbound_audio._queue.get_nowait()
    voice_starts = [
        message for message in channel.messages if message["type"] == "voice.speech_start"
    ]
    voice_ends = [message for message in channel.messages if message["type"] == "voice.speech_end"]

    assert first == "你好:a".encode()
    assert second == "你好:b".encode()
    assert len(voice_starts) == 1
    assert len(voice_ends) == 1


@pytest.mark.asyncio
async def test_audio_commit_transcribes_and_starts_agent_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_build_agent(_config: AgentConfig) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("asuka.core.voice.session.build_agent", fake_build_agent)
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        asr_provider=FakeAsr(),
        tts_provider=FakeTts(),
    )
    channel = FakeDataChannel()
    session.data_channel = channel

    speech_pcm = b"\x10\x20" * 8_000
    result = session._vad.consume(speech_pcm)
    assert result.speech_started

    await session.handle_data_message(json.dumps({"type": "input.audio.commit", "payload": {}}))
    if session._asr_tasks:
        await asyncio.gather(*session._asr_tasks)
    if session._active_task:
        await session._active_task

    event_types = [message["type"] for message in channel.messages]
    assert "input.speech_end" in event_types
    assert any(
        message["type"] == "input.transcript.final"
        and message["payload"] == {"text": "后端转写"}
        for message in channel.messages
    )
    assert "asr_not_configured" not in json.dumps(channel.messages, ensure_ascii=False)


@pytest.mark.asyncio
async def test_invalid_datachannel_json_returns_error() -> None:
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=FakeTts(),
    )
    channel = FakeDataChannel()
    session.data_channel = channel

    await session.handle_data_message("{")

    assert channel.messages[0]["type"] == "error"
    assert channel.messages[0]["payload"]["message"] == "invalid realtime event JSON"


@pytest.mark.asyncio
async def test_cancel_turn_cancels_producer_before_draining_tts() -> None:
    """A cancelled agent turn must not leave orphan TTS tasks for the next turn.

    The producer (agent turn) is cancelled first so it cannot schedule new TTS
    tasks while the existing ones are drained; otherwise stale sentences survive
    into the next turn and play back out of order.
    """

    class BlockingTts:
        def __init__(self) -> None:
            self.gate = asyncio.Event()

        async def synthesize(self, text: str, **_kwargs: Any) -> SynthesizedPcm:
            await self.gate.wait()
            return SynthesizedPcm(pcm=b"\x00\x00", sample_rate=48_000)

    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=BlockingTts(),
    )
    session.data_channel = FakeDataChannel()
    session._active_tts_turn_id = "T"
    session.active_turn_id = "T"

    async def producer() -> None:
        index = 0
        while True:
            session._schedule_tts(f"句{index}", "T")
            index += 1
            await asyncio.sleep(0.001)

    session._active_task = asyncio.create_task(producer())
    await asyncio.sleep(0.01)
    assert session._tts_tasks  # producer scheduled blocked TTS tasks

    await session.cancel_turn()

    assert session._active_task is None
    assert session._tts_tasks == set()
    assert session._active_tts_turn_id is None
    assert session._next_tts_sequence == 0


@pytest.mark.asyncio
async def test_chat_cancel_clears_queued_audio() -> None:
    session = RealtimeVoiceSession(
        session_id="rt_test",
        conversation_id="conv_test",
        agent_config=AgentConfig(),
        tts_provider=FakeTts(),
    )
    session.outbound_audio.enqueue_pcm(b"\x20\x00" * 960, sample_rate=48_000)

    await session.cancel_turn()
    frame = await session.outbound_audio.recv()

    assert bytes(frame.planes[0]) == bytes(frame.planes[0].buffer_size)
