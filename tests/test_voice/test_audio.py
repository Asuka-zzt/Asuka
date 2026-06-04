"""Realtime audio VAD and outbound queue tests."""

import pytest

from asuka.core.voice.audio import QueuedAudioTrack, RmsVadSegmenter


def test_vad_ignores_silence() -> None:
    vad = RmsVadSegmenter(
        rms_threshold=0.01,
        min_speech_ms=300,
        silence_ms=700,
        max_speech_ms=20_000,
    )

    result = vad.consume(bytes(16_000))

    assert not result.speech_started
    assert result.segments == []


def test_vad_commits_valid_speech_after_silence() -> None:
    vad = RmsVadSegmenter(
        rms_threshold=0.01,
        min_speech_ms=300,
        silence_ms=700,
        max_speech_ms=20_000,
    )

    speech = b"\x20\x20" * 8_000
    silence = bytes(24_000)
    result = vad.consume(speech + silence)

    assert result.speech_started
    assert len(result.segments) == 1
    assert result.segments[0].duration_ms >= 1_000


def test_vad_forces_commit_at_max_duration() -> None:
    vad = RmsVadSegmenter(
        rms_threshold=0.01,
        min_speech_ms=300,
        silence_ms=700,
        max_speech_ms=500,
    )

    result = vad.consume(b"\x20\x20" * 12_000)

    assert result.speech_started
    assert result.segments
    assert result.segments[0].duration_ms >= 500


@pytest.mark.asyncio
async def test_queued_audio_track_returns_non_silence_frame() -> None:
    track = QueuedAudioTrack()
    track.enqueue_pcm(b"\x20\x00" * 960, sample_rate=48_000)

    frame = await track.recv()

    assert bytes(frame.planes[0]) != bytes(frame.planes[0].buffer_size)


@pytest.mark.asyncio
async def test_queued_audio_track_resamples_to_output_rate() -> None:
    track = QueuedAudioTrack()
    track.enqueue_pcm(b"\x20\x00" * 320, sample_rate=16_000)

    frame = await track.recv()

    assert frame.sample_rate == 48_000
    assert frame.samples == 960
    assert bytes(frame.planes[0]) != bytes(frame.planes[0].buffer_size)
