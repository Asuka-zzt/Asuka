"""Realtime WebRTC session implementation."""

import asyncio
import json
import time
import uuid
from typing import Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from av.audio.frame import AudioFrame
from langchain_core.messages import HumanMessage

from asuka.config import get_settings
from asuka.core.agent.model import AgentConfig
from asuka.core.graph.dispatch import build_agent
from asuka.core.voice.asr import AsrProvider, get_asr_provider
from asuka.core.voice.audio import AudioFrameToPcm16Mono, QueuedAudioTrack, RmsVadSegmenter
from asuka.core.voice.tts import (
    RealtimeTtsProvider,
    RealtimeTtsStream,
    get_tts_provider,
    sentence_segments,
)
from asuka.routes.ws import (
    LANGUAGE_TOOL_NAMES,
    Live2DTagExtractor,
    ToolJsonStripper,
    _jsonable_tool_payload,
    _tool_name,
)

# How many sentences may be synthesized ahead of the one currently playing.
TTS_PREFETCH_DEPTH = 3


class RealtimeVoiceSession:
    """A single WebRTC + DataChannel session bound to one conversation."""

    def __init__(
        self,
        *,
        session_id: str,
        conversation_id: str,
        agent_config: AgentConfig,
        language: str | None = None,
        voice: str | None = None,
        asr_provider: AsrProvider | None = None,
        tts_provider: RealtimeTtsProvider | None = None,
    ) -> None:
        settings = get_settings()
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.agent_config = agent_config
        self.language = language
        self.voice = voice
        self.asr_provider = asr_provider or get_asr_provider()
        self.tts_provider = tts_provider or get_tts_provider()
        # Reuse one TTS connection across this session's sentences when the
        # provider supports it, so sentences after the first skip the per-
        # sentence connection handshake. The connection is opened lazily.
        open_stream = getattr(self.tts_provider, "open_stream", None)
        self._tts_stream: RealtimeTtsStream | None = (
            open_stream() if callable(open_stream) else None
        )
        self.outbound_audio = QueuedAudioTrack(sample_rate=settings.piper_sample_rate)
        self._audio_converter = AudioFrameToPcm16Mono()
        self._vad = RmsVadSegmenter(
            rms_threshold=settings.voice_vad_rms_threshold,
            min_speech_ms=settings.voice_vad_min_speech_ms,
            silence_ms=settings.voice_vad_silence_ms,
            max_speech_ms=settings.voice_vad_max_speech_ms,
        )
        self.peer_connection: Any | None = None
        self.data_channel: Any | None = None
        self.active_turn_id: str | None = None
        self._active_tts_turn_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._track_tasks: set[asyncio.Task[None]] = set()
        self._asr_tasks: set[asyncio.Task[None]] = set()
        self._tts_tasks: set[asyncio.Task[None]] = set()
        self._tts_condition = asyncio.Condition()
        self._next_tts_sequence = 0
        self._next_tts_enqueue_sequence = 0
        self._skipped_tts_sequences: set[int] = set()
        # Render upcoming sentences concurrently so a streaming provider's
        # per-sentence connection/handshake latency overlaps with playback of
        # earlier sentences instead of draining the outbound queue to silence.
        self._tts_semaphore = asyncio.Semaphore(TTS_PREFETCH_DEPTH)
        self.created_at = time.time()
        self.last_seen_at = self.created_at

    async def attach_offer(self, offer: RTCSessionDescription) -> RTCSessionDescription:
        """Attach a browser offer and return an SDP answer."""
        pc = RTCPeerConnection()
        self.peer_connection = pc
        pc.addTrack(self.outbound_audio)

        @pc.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            self._attach_data_channel(channel)

        @pc.on("track")
        def on_track(track: Any) -> None:
            if track.kind == "audio":
                task = asyncio.create_task(self._drain_audio_track(track))
                self._track_tasks.add(task)
                task.add_done_callback(self._track_tasks.discard)

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return pc.localDescription

    def _attach_data_channel(self, channel: Any) -> None:
        self.data_channel = channel

        @channel.on("open")  # type: ignore[untyped-decorator]
        def on_open() -> None:
            self.send_event("session.ready")

        @channel.on("message")  # type: ignore[untyped-decorator]
        def on_message(message: str | bytes) -> None:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            asyncio.create_task(self.handle_data_message(message))

    async def _drain_audio_track(self, track: Any) -> None:
        """Run inbound mic frames through VAD and ASR."""
        while True:
            try:
                frame = await track.recv()
            except Exception:  # noqa: BLE001
                return
            if not isinstance(frame, AudioFrame):
                continue
            pcm = self._audio_converter.convert(frame)
            result = self._vad.consume(pcm)
            if result.speech_started:
                self.send_event("input.speech_start")
            for segment in result.segments:
                self._schedule_asr(segment.pcm, segment.sample_rate, segment.duration_ms)

    async def handle_data_message(self, message: str) -> None:
        self.last_seen_at = time.time()
        try:
            raw = json.loads(message)
        except json.JSONDecodeError:
            self.send_event("error", {"message": "invalid realtime event JSON"})
            return

        event_type = raw.get("type")
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}

        if event_type == "text.send":
            content = str(payload.get("content", "")).strip()
            if content:
                await self.start_turn(content)
        elif event_type == "session.update":
            self.language = payload.get("language") or self.language
            self.voice = payload.get("voice") or self.voice
            self.send_event("session.ready")
        elif event_type == "chat.cancel":
            await self.cancel_turn()
        elif event_type == "ping":
            self.send_event("pong", {"ts": payload.get("ts")})
        elif event_type == "input.audio.commit":
            segment = self._vad.commit()
            if segment is not None:
                self._schedule_asr(segment.pcm, segment.sample_rate, segment.duration_ms)
        else:
            self.send_event("error", {"message": f"unsupported event type: {event_type}"})

    async def start_turn(
        self,
        user_text: str,
        *,
        emit_transcript: bool = True,
        cancel_asr: bool = True,
    ) -> None:
        await self.cancel_turn(cancel_asr=cancel_asr)
        turn_id = uuid.uuid4().hex
        self.active_turn_id = turn_id
        self._active_tts_turn_id = turn_id
        self._reset_tts_order()
        self._active_task = asyncio.create_task(
            self._run_agent_turn(user_text, turn_id, emit_transcript=emit_transcript)
        )

    async def cancel_turn(self, *, cancel_asr: bool = True) -> None:
        current_task = asyncio.current_task()
        self._vad.clear()
        self.outbound_audio.clear()

        # Cancel the agent turn (the producer) first and wait for it to stop, so
        # it cannot schedule new TTS tasks while we are draining the existing
        # ones. Otherwise orphaned sentences from the old turn would survive into
        # the next turn's (reset) sequence space and play back out of order.
        active = self._active_task
        if active is not None and active is not current_task and not active.done():
            active.cancel()
            try:
                await active
            except asyncio.CancelledError:
                pass
        self._active_task = None

        if cancel_asr:
            for task in list(self._asr_tasks):
                if task is not current_task and not task.done():
                    task.cancel()
            if self._asr_tasks:
                await asyncio.gather(*self._asr_tasks, return_exceptions=True)
            self._asr_tasks = {task for task in self._asr_tasks if not task.done()}

        for task in list(self._tts_tasks):
            if task is not current_task and not task.done():
                task.cancel()
        if self._tts_tasks:
            await asyncio.gather(*self._tts_tasks, return_exceptions=True)
        self._tts_tasks = {task for task in self._tts_tasks if not task.done()}

        self.active_turn_id = None
        self._active_tts_turn_id = None
        self._reset_tts_order()

    def _schedule_asr(self, pcm: bytes, sample_rate: int, duration_ms: int) -> None:
        task = asyncio.create_task(self._transcribe_segment(pcm, sample_rate, duration_ms))
        self._asr_tasks.add(task)
        task.add_done_callback(self._asr_tasks.discard)

    async def _transcribe_segment(self, pcm: bytes, sample_rate: int, duration_ms: int) -> None:
        self.send_event("input.speech_end", {"durationMs": duration_ms})
        try:
            text = (
                await self.asr_provider.transcribe(
                    pcm,
                    sample_rate=sample_rate,
                    language=self.language,
                )
            ).strip()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.send_event("error", {"message": f"ASR failed: {exc}", "code": "asr_failed"})
            return

        self.send_event("input.transcript.final", {"text": text})
        if text:
            await self.start_turn(text, emit_transcript=False, cancel_asr=False)

    async def _run_agent_turn(
        self,
        user_text: str,
        turn_id: str,
        *,
        emit_transcript: bool,
    ) -> None:
        config = {"configurable": {"thread_id": self.conversation_id}}
        extractor = Live2DTagExtractor()
        json_stripper = ToolJsonStripper()
        speech_buffer = ""

        try:
            agent = await build_agent(self.agent_config)
            if emit_transcript:
                self.send_event("input.transcript.final", {"text": user_text}, turn_id=turn_id)
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=user_text)]},
                config=config,
                version="v2",
            ):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content
                    if content and isinstance(content, str):
                        visible_content = json_stripper.feed(content)
                        clean, evts = extractor.feed(visible_content)
                        for evt in evts:
                            self._send_live2d_event(evt, turn_id)
                        if clean:
                            self.send_event("chat.token", {"content": clean}, turn_id=turn_id)
                            speech_buffer += clean
                            segments, speech_buffer = sentence_segments(
                                speech_buffer,
                                eager=True,
                            )
                            for segment in segments:
                                self._schedule_tts(segment, turn_id)
                elif event["event"] == "on_tool_end":
                    name = _tool_name(event)
                    if name in LANGUAGE_TOOL_NAMES:
                        self.send_event(
                            "tool.result",
                            {
                                "name": name,
                                "payload": _jsonable_tool_payload(
                                    event.get("data", {}).get("output")
                                ),
                            },
                            turn_id=turn_id,
                        )

            tail = json_stripper.flush()
            remaining = ""
            if tail:
                clean_tail, evts = extractor.feed(tail)
                for evt in evts:
                    self._send_live2d_event(evt, turn_id)
                remaining += clean_tail
                remaining += extractor.flush()
            if remaining:
                self.send_event("chat.token", {"content": remaining}, turn_id=turn_id)
                speech_buffer += remaining

            segments, speech_buffer = sentence_segments(speech_buffer, force=True)
            for segment in segments:
                self._schedule_tts(segment, turn_id)

            self.send_event("done", {}, turn_id=turn_id)
        except asyncio.CancelledError:
            self.send_event("done", {"cancelled": True}, turn_id=turn_id)
            raise
        except Exception as exc:  # noqa: BLE001
            self.send_event("error", {"message": str(exc)}, turn_id=turn_id)
        finally:
            if self.active_turn_id == turn_id:
                self.active_turn_id = None
                self._active_task = None

    def _schedule_tts(self, text: str, turn_id: str) -> None:
        sequence = self._next_tts_sequence
        self._next_tts_sequence += 1
        task = asyncio.create_task(self._synthesize_sentence(text, turn_id, sequence))
        self._tts_tasks.add(task)
        task.add_done_callback(self._tts_tasks.discard)

    async def _synthesize_sentence(self, text: str, turn_id: str, sequence: int) -> None:
        speech_started = False
        try:
            # Render concurrently (bounded by the prefetch semaphore) so this
            # sentence's synthesis overlaps with playback of earlier sentences.
            async with self._tts_semaphore:
                if not self._is_tts_turn_current(turn_id):
                    await self._skip_tts_sequence(sequence)
                    return
                chunks, sample_rate = await self._render_pcm(text)

            # Enqueue strictly in sentence order once it is this sequence's turn.
            await self._wait_for_tts_turn(sequence)
            if not self._is_tts_turn_current(turn_id):
                await self._skip_tts_sequence(sequence)
                return
            self.send_event("voice.speech_start", {"text": text}, turn_id=turn_id)
            speech_started = True
            for pcm in chunks:
                self.outbound_audio.enqueue_pcm(pcm, sample_rate=sample_rate)
            self.send_event("voice.speech_end", {"text": text}, turn_id=turn_id)
            await self._advance_tts_sequence()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            if speech_started:
                self.send_event("voice.speech_end", {"text": text, "failed": True}, turn_id=turn_id)
            self.send_event("error", {"message": f"TTS failed: {exc}", "code": "tts_failed"})
            await self._skip_tts_sequence(sequence)

    async def _render_pcm(self, text: str) -> tuple[list[bytes], int]:
        """Synthesize a sentence into ordered PCM chunks plus their sample rate."""
        chunks: list[bytes] = []
        sample_rate = self.outbound_audio.sample_rate
        if self._tts_stream is not None:
            audio = await self._tts_stream.render(text, language=self.language)
            return ([audio.pcm] if audio.pcm else []), audio.sample_rate
        stream_synthesize = getattr(self.tts_provider, "stream_synthesize", None)
        if callable(stream_synthesize):
            async for audio in stream_synthesize(text, language=self.language):
                if audio.pcm:
                    chunks.append(audio.pcm)
                    sample_rate = audio.sample_rate
        else:
            audio = await self.tts_provider.synthesize(text, language=self.language)
            if audio.pcm:
                chunks.append(audio.pcm)
                sample_rate = audio.sample_rate
        return chunks, sample_rate

    def _is_tts_turn_current(self, turn_id: str) -> bool:
        return self._active_tts_turn_id == turn_id

    async def _wait_for_tts_turn(self, sequence: int) -> None:
        async with self._tts_condition:
            await self._tts_condition.wait_for(
                lambda: sequence == self._next_tts_enqueue_sequence
            )

    async def _advance_tts_sequence(self) -> None:
        async with self._tts_condition:
            self._next_tts_enqueue_sequence += 1
            while self._next_tts_enqueue_sequence in self._skipped_tts_sequences:
                self._skipped_tts_sequences.remove(self._next_tts_enqueue_sequence)
                self._next_tts_enqueue_sequence += 1
            self._tts_condition.notify_all()

    async def _skip_tts_sequence(self, sequence: int) -> None:
        async with self._tts_condition:
            self._skipped_tts_sequences.add(sequence)
            while self._next_tts_enqueue_sequence in self._skipped_tts_sequences:
                self._skipped_tts_sequences.remove(self._next_tts_enqueue_sequence)
                self._next_tts_enqueue_sequence += 1
            self._tts_condition.notify_all()

    def _reset_tts_order(self) -> None:
        self._next_tts_sequence = 0
        self._next_tts_enqueue_sequence = 0
        self._skipped_tts_sequences.clear()

    def _send_live2d_event(self, raw_event: dict[str, Any], turn_id: str) -> None:
        payload = {key: value for key, value in raw_event.items() if key != "type"}
        self.send_event("live2d.emotion", payload, turn_id=turn_id)

    def send_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        turn_id: str | None = None,
    ) -> None:
        channel = self.data_channel
        if not channel or channel.readyState != "open":
            return
        channel.send(
            json.dumps(
                {
                    "type": event_type,
                    "id": uuid.uuid4().hex,
                    "conversationId": self.conversation_id,
                    "sessionId": self.session_id,
                    "turnId": turn_id,
                    "createdAt": int(time.time() * 1000),
                    "payload": payload or {},
                },
                ensure_ascii=False,
            )
        )

    async def close(self) -> None:
        await self.cancel_turn()
        for task in list(self._track_tasks):
            task.cancel()
        if self._track_tasks:
            await asyncio.gather(*self._track_tasks, return_exceptions=True)
        self._track_tasks.clear()
        if self._tts_stream is not None:
            await self._tts_stream.aclose()
        if self.peer_connection is not None:
            await self.peer_connection.close()
            self.peer_connection = None
