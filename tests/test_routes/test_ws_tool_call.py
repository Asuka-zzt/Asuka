"""WebSocket 端验证：对话 Agent 触发工具调用的完整接线（零 token，全程 mock）。

不验证“真实 LLM 是否会自主决定调用”（那需要真实 token，已在手动验收中跑通子图）；
这里用假模型发出 tool_call，证明 WS → create_agent → 工具注册表 → 工具执行 → 回流 这一链路通畅。
"""

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

from asukabot.core.graph import dispatch
from asukabot.routes import ws


class FakeToolCallingModel(BaseChatModel):
    """按序返回预置消息的假模型；bind_tools 返回自身。"""

    _responses: list[BaseMessage] = PrivateAttr(default_factory=list)
    _idx: int = PrivateAttr(default=0)

    def __init__(self, responses: Sequence[BaseMessage], **kw: Any) -> None:
        super().__init__(**kw)
        self._responses = list(responses)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeToolCallingModel":
        return self

    def _generate(self, messages: Any, stop: Any = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        i = min(self._idx, len(self._responses) - 1)
        if self._idx < len(self._responses) - 1:
            self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=self._responses[i])])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"


@pytest.fixture
def ws_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, dict[str, Any]]]:
    """构建仅含 ws 路由的 app，注入假模型 + 桩工具 + 内存 checkpointer。"""
    called: dict[str, Any] = {}

    @tool
    async def generate_wiki(project_path: str, language: str = "chinese") -> str:
        """为指定本地代码目录生成 Wiki 教程文档。"""
        called["project_path"] = project_path
        called["language"] = language
        return "已生成 Wiki：/fake/out（index.md + 2 个章节页）"

    responses = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "generate_wiki",
                "args": {"project_path": "ref/normal_agent/astrbot"},
                "id": "call_1",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="已经帮你把 wiki 生成好了。"),
    ]

    async def fake_checkpointer() -> MemorySaver:
        return MemorySaver()

    monkeypatch.setattr(dispatch, "_agent", None)
    monkeypatch.setattr(dispatch, "get_llm", lambda _m: FakeToolCallingModel(responses))
    monkeypatch.setattr(dispatch, "get_tools_for_agent", lambda _id: [generate_wiki])
    monkeypatch.setattr(dispatch, "get_checkpointer", fake_checkpointer)

    app = FastAPI()
    app.include_router(ws.router)
    yield app, called


def test_ws_agent_invokes_tool(ws_app: tuple[FastAPI, dict[str, Any]]) -> None:
    app, called = ws_app
    client = TestClient(app)
    with client.websocket_connect("/ws/conv-tool") as websocket:
        websocket.send_json({"message": "帮我给 ref/normal_agent/astrbot 生成 wiki"})
        events: list[dict[str, Any]] = []
        while True:
            evt = websocket.receive_json()
            events.append(evt)
            if evt["type"] in ("done", "error"):
                break

    # 工具被真实执行，且拿到了 Agent 解析出的参数
    assert called.get("project_path") == "ref/normal_agent/astrbot"
    # 链路正常收尾，没有异常下发
    types = [e["type"] for e in events]
    assert "error" not in types
    assert types[-1] == "done"
