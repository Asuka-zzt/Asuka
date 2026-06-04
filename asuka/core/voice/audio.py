"""Audio utilities for realtime WebRTC voice sessions."""

import asyncio
import time
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from aiortc.mediastreams import AudioStreamTrack
from av.audio.frame import AudioFrame
from av.audio.resampler import AudioResampler

INPUT_SAMPLE_RATE = 16_000
OUTPUT_SAMPLE_RATE = 48_000
OUTPUT_SAMPLES_PER_FRAME = 960
SAMPLE_WIDTH_BYTES = 2


@dataclass(frozen=True)
class SpeechSegment:
    """Committed speech PCM captured by VAD."""

    pcm: bytes
    sample_rate: int
    duration_ms: int


@dataclass(frozen=True)
class VadConsumeResult:
    """VAD events produced by feeding PCM."""

    speech_started: bool = False
    segments: list[SpeechSegment] = field(default_factory=list)


def pcm16_rms(pcm: bytes) -> float:
    """Return normalized RMS for little-endian s16 PCM."""
    if not pcm:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    normalized = samples.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(normalized * normalized)))


def resample_pcm16_mono(pcm: bytes, *, source_rate: int, target_rate: int) -> bytes:
    """Resample mono s16 PCM to another rate."""
    if not pcm or source_rate == target_rate:
        return pcm

    samples = np.frombuffer(pcm, dtype=np.int16)
    frame = AudioFrame(format="s16", layout="mono", samples=samples.size)
    frame.planes[0].update(samples.tobytes())
    frame.sample_rate = source_rate
    frame.time_base = Fraction(1, source_rate)

    resampler = AudioResampler(format="s16", layout="mono", rate=target_rate)
    output = bytearray()
    for converted in resampler.resample(frame):
        output.extend(bytes(converted.planes[0]))
    for converted in resampler.resample(None):
        output.extend(bytes(converted.planes[0]))
    return bytes(output)


class AudioFrameToPcm16Mono:
    """Convert arbitrary PyAV audio frames to mono s16 PCM."""

    def __init__(self, sample_rate: int = INPUT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._resampler = AudioResampler(format="s16", layout="mono", rate=sample_rate)

    def convert(self, frame: AudioFrame) -> bytes:
        """Convert a WebRTC AudioFrame into mono s16 PCM bytes."""
        output = bytearray()
        for converted in self._resampler.resample(frame):
            output.extend(bytes(converted.planes[0]))
        return bytes(output)


class RmsVadSegmenter:
    """Simple RMS VAD that commits complete speech segments."""

    def __init__(
        self,
        *,
        sample_rate: int = INPUT_SAMPLE_RATE,
        rms_threshold: float,
        min_speech_ms: int,
        silence_ms: int,
        max_speech_ms: int,
    ) -> None:
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self.min_speech_ms = min_speech_ms
        self.silence_ms = silence_ms
        self.max_speech_ms = max_speech_ms
        self._chunk_bytes = self._bytes_for_ms(20)
        self._buffer = bytearray()
        self._silence_ms = 0
        self._in_speech = False

    def consume(self, pcm: bytes) -> VadConsumeResult:
        """Feed PCM and return VAD events."""
        speech_started = False
        segments: list[SpeechSegment] = []
        offset = 0

        while offset < len(pcm):
            chunk = pcm[offset : offset + self._chunk_bytes]
            offset += len(chunk)
            if not chunk:
                continue

            chunk_ms = self._duration_ms(len(chunk))
            voiced = pcm16_rms(chunk) >= self.rms_threshold

            if not self._in_speech:
                if voiced:
                    self._in_speech = True
                    speech_started = True
                    self._silence_ms = 0
                    self._buffer.extend(chunk)
                continue

            self._buffer.extend(chunk)
            if voiced:
                self._silence_ms = 0
            else:
                self._silence_ms += chunk_ms

            if self._duration_ms(len(self._buffer)) >= self.max_speech_ms:
                segment = self.commit()
                if segment is not None:
                    segments.append(segment)
            elif self._silence_ms >= self.silence_ms:
                segment = self.commit()
                if segment is not None:
                    segments.append(segment)

        return VadConsumeResult(speech_started=speech_started, segments=segments)

    def commit(self) -> SpeechSegment | None:
        """Commit the current speech buffer if it is long enough."""
        if not self._buffer:
            self.clear()
            return None

        pcm = bytes(self._buffer)
        duration_ms = self._duration_ms(len(pcm))
        self.clear()
        if duration_ms < self.min_speech_ms:
            return None
        return SpeechSegment(pcm=pcm, sample_rate=self.sample_rate, duration_ms=duration_ms)

    def clear(self) -> None:
        """Reset the active VAD buffer."""
        self._buffer.clear()
        self._silence_ms = 0
        self._in_speech = False

    def _bytes_for_ms(self, duration_ms: int) -> int:
        samples = int(self.sample_rate * duration_ms / 1000)
        return max(SAMPLE_WIDTH_BYTES, samples * SAMPLE_WIDTH_BYTES)

    def _duration_ms(self, byte_count: int) -> int:
        samples = byte_count // SAMPLE_WIDTH_BYTES
        return int(samples * 1000 / self.sample_rate)


class QueuedAudioTrack(AudioStreamTrack):
    """Outbound 48kHz mono PCM track backed by an async byte queue."""

    kind = "audio"

    def __init__(
        self,
        *,
        sample_rate: int = OUTPUT_SAMPLE_RATE,
        samples_per_frame: int = OUTPUT_SAMPLES_PER_FRAME,
    ) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.samples_per_frame = samples_per_frame
        self._timestamp = 0
        self._clock_start: float | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._pending = bytearray()

    async def recv(self) -> AudioFrame:
        """Return the next audio frame, padding with silence when idle."""
        # Pace frames against an absolute clock so scheduling jitter and
        # processing time do not accumulate into timestamp drift. A fixed
        # ``sleep(frame_ms)`` per call drifts slower than realtime and starves
        # the receiver's jitter buffer, which is heard as stuttering.
        if self._clock_start is None:
            self._clock_start = time.monotonic()
        else:
            # ``_timestamp`` is the pts of the frame about to be produced, i.e.
            # its presentation offset from ``_clock_start``.
            target = self._clock_start + self._timestamp / self.sample_rate
            wait = target - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
        target_bytes = self.samples_per_frame * SAMPLE_WIDTH_BYTES

        while len(self._pending) < target_bytes:
            try:
                self._pending.extend(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if self._pending:
            payload = bytes(self._pending[:target_bytes])
            del self._pending[:target_bytes]
            payload += bytes(target_bytes - len(payload))
        else:
            payload = bytes(target_bytes)

        frame = AudioFrame(format="s16", layout="mono", samples=self.samples_per_frame)
        frame.planes[0].update(payload)
        frame.pts = self._timestamp
        frame.sample_rate = self.sample_rate
        frame.time_base = Fraction(1, self.sample_rate)
        self._timestamp += self.samples_per_frame
        return frame

    def enqueue_pcm(self, pcm: bytes, *, sample_rate: int) -> None:
        """Add mono s16 PCM to the outbound track queue.

        Each call carries one complete synthesized sentence, so it is resampled
        independently (and fully flushed). A resampler reused across calls keeps
        an internal FIFO and bleeds one sentence's samples into the next, which
        is heard as an earlier sentence replaying under later ones.
        """
        if not pcm:
            return
        payload = resample_pcm16_mono(pcm, source_rate=sample_rate, target_rate=self.sample_rate)
        if payload:
            self._queue.put_nowait(payload)

    def clear(self) -> None:
        """Drop pending synthesized audio."""
        self._pending.clear()
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
