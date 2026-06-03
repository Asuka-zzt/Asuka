"""工具注册表与 generate_wiki 工具。"""

from pathlib import Path
from typing import Any

import pytest

from asuka.core.tools import get_tools_for_agent
from asuka.core.tools.wiki_generator import generate_wiki


def test_registry_contains_wiki() -> None:
    names = [t.name for t in get_tools_for_agent("default")]
    assert "generate_wiki" in names


def test_teacher_registry_contains_language_tools_only() -> None:
    names = [t.name for t in get_tools_for_agent("english_teacher")]
    assert "correct_text" in names
    assert "generate_quiz" in names
    assert "generate_wiki" not in names


def test_japanese_teacher_registry_contains_language_tools_only() -> None:
    names = [t.name for t in get_tools_for_agent("japanese_teacher")]
    assert "correct_text" in names
    assert "generate_quiz" in names
    assert "generate_wiki" not in names


async def test_generate_wiki_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def fake_ainvoke(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "final_output_dir": str(tmp_path / "demo"),
            "chapters": [{"chapter_num": 1, "content": "x"}],
        }

    class FakeGraph:
        ainvoke = staticmethod(fake_ainvoke)

    monkeypatch.setattr(
        "asuka.core.tools.wiki_generator.build_wiki_graph", lambda: FakeGraph()
    )
    result = await generate_wiki.ainvoke({"project_path": str(tmp_path)})
    assert "已生成 Wiki" in result
    assert "1 个章节" in result
