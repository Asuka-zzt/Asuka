"""WebSocket 端验证：语言老师工具结果以 tool.result 事件下发。"""

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from asuka.core.graph import dispatch
from asuka.routes import ws


class FakeLanguageToolModel(BaseChatModel):
    """按序返回工具调用与最终回复。"""

    _responses: list[BaseMessage] = PrivateAttr(default_factory=list)
    _idx: int = PrivateAttr(default=0)

    def __init__(self, responses: Sequence[BaseMessage], **kw: Any) -> None:
        super().__init__(**kw)
        self._responses = list(responses)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeLanguageToolModel":
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        i = min(self._idx, len(self._responses) - 1)
        if self._idx < len(self._responses) - 1:
            self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=self._responses[i])])

    @property
    def _llm_type(self) -> str:
        return "fake-language-tool"


@pytest.fixture
def ws_language_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """构建仅含 ws 路由的 app，注入语言工具与假模型。"""

    @tool
    async def correct_text(
        text: str,
        language: str,
        level: str | None = None,
    ) -> dict[str, Any]:
        """批改目标语文本，返回结构化纠错结果。"""
        return {
            "has_error": True,
            "language": language,
            "items": [
                {
                    "error_type": "主谓一致",
                    "original": "I has",
                    "corrected": "I have",
                    "explanation_zh": f"{level} 水平下，I 后面要用 have。",
                }
            ],
            "natural_rewrite": "I have an apple.",
            "annotation": "/aɪ hæv ən ˈæpəl/",
            "encouragement_zh": "这个改法会自然很多。",
        }

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "correct_text",
                    "args": {
                        "text": "I has a apple.",
                        "language": "english",
                        "level": "A2",
                    },
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="这句已经批改好了。"),
    ]

    async def fake_checkpointer() -> MemorySaver:
        return MemorySaver()

    monkeypatch.setattr(dispatch, "_agents", {})
    monkeypatch.setattr(
        dispatch,
        "get_llm",
        lambda _m: FakeLanguageToolModel(responses),
    )
    monkeypatch.setattr(dispatch, "get_tools_for_agent", lambda _id: [correct_text])
    monkeypatch.setattr(dispatch, "get_checkpointer", fake_checkpointer)

    app = FastAPI()
    app.include_router(ws.router)
    yield app


def test_ws_language_tool_result_event(ws_language_app: FastAPI) -> None:
    client = TestClient(ws_language_app)
    with client.websocket_connect("/ws/conv-language") as websocket:
        websocket.send_json(
            {
                "message": "帮我批改 I has a apple.",
                "persona_id": "english_teacher",
                "level": "A2",
            }
        )
        events: list[dict[str, Any]] = []
        while True:
            evt = websocket.receive_json()
            events.append(evt)
            if evt["type"] in ("done", "error"):
                break

    tool_events = [evt for evt in events if evt["type"] == "tool.result"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "correct_text"
    assert "natural_rewrite" in tool_events[0]["payload"], tool_events[0]["payload"]
    assert tool_events[0]["payload"]["natural_rewrite"] == "I have an apple."
    assert tool_events[0]["payload"]["language"] == "english"
    assert events[-1]["type"] == "done"
