"""TTS REST route."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from asukabot.routes import tts


@pytest.fixture
def tts_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Build a TTS-only app with provider synthesis mocked."""

    async def fake_synthesize(text: str, voice: str | None = None) -> bytes:
        return f"audio:{voice or 'default'}:{text}".encode()

    monkeypatch.setattr(tts.tts_provider, "synthesize_speech", fake_synthesize)
    app = FastAPI()
    app.include_router(tts.router)
    yield app


def test_tts_route_returns_audio(tts_app: FastAPI) -> None:
    client = TestClient(tts_app)
    response = client.post("/api/tts", json={"text": "你好", "voice": "test-voice"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == "audio:test-voice:你好".encode()


def test_tts_route_rejects_blank_text(tts_app: FastAPI) -> None:
    client = TestClient(tts_app)
    response = client.post("/api/tts", json={"text": "   "})

    assert response.status_code == 422
