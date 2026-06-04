"""Realtime signaling routes."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from asuka.core.voice.manager import realtime_session_manager
from asuka.routes import realtime


@pytest.fixture
def realtime_app() -> Iterator[FastAPI]:
    app = FastAPI()
    app.include_router(realtime.router)
    yield app


def test_create_realtime_session(realtime_app: FastAPI) -> None:
    client = TestClient(realtime_app)
    response = client.post(
        "/api/realtime/sessions",
        json={"conversation_id": "conv-route"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"].startswith("rt_")
    assert payload["conversation_id"] == "conv-route"

    closed = client.delete(f"/api/realtime/sessions/{payload['session_id']}")
    assert closed.status_code == 200


def test_offer_for_missing_realtime_session_returns_404(realtime_app: FastAPI) -> None:
    client = TestClient(realtime_app)
    response = client.post(
        "/api/realtime/sessions/rt_missing/offer",
        json={"sdp": "v=0\r\n", "type": "offer"},
    )

    assert response.status_code == 404


@pytest.fixture(autouse=True)
def cleanup_realtime_sessions() -> Iterator[None]:
    yield
    for session_id in list(realtime_session_manager._sessions):
        realtime_session_manager._sessions.pop(session_id, None)
