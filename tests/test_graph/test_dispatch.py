"""Agent dispatch 缓存行为。"""

from typing import Any

import pytest

from asuka.core.agent.presets import english_teacher, japanese_teacher
from asuka.core.graph import dispatch


async def test_build_agent_caches_by_persona_and_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, Any]] = []

    def fake_create_agent(**kwargs: Any) -> dict[str, Any]:
        created.append(kwargs)
        return {"index": len(created), **kwargs}

    monkeypatch.setattr(dispatch, "_agents", {})
    monkeypatch.setattr(dispatch, "create_agent", fake_create_agent)
    monkeypatch.setattr(dispatch, "get_llm", lambda _model_id: object())
    monkeypatch.setattr(dispatch, "get_tools_for_agent", lambda agent_id: [agent_id])

    async def fake_checkpointer() -> object:
        return object()

    monkeypatch.setattr(dispatch, "get_checkpointer", fake_checkpointer)

    english_a2_first = await dispatch.build_agent(english_teacher("A2"))
    english_a2_second = await dispatch.build_agent(english_teacher("A2"))
    english_b1 = await dispatch.build_agent(english_teacher("B1"))
    japanese_n5 = await dispatch.build_agent(japanese_teacher("N5"))

    assert english_a2_first is english_a2_second
    assert english_a2_first is not english_b1
    assert english_b1 is not japanese_n5
    assert len(created) == 3
