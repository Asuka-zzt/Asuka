"""测试共用 fixtures：用假 LLM 替代真实调用，构造样例项目目录。"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from asukabot.core.graph.wiki.state import (
    Abstraction,
    IdentifyResult,
    OrderResult,
    Relationship,
    RelationshipsResult,
)


class _StructuredRunnable:
    """模拟 llm.with_structured_output(Schema) 返回的 Runnable。"""

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    async def ainvoke(self, _prompt: Any, *args: Any, **kwargs: Any) -> Any:
        return self._obj


class FakeWikiLLM:
    """假 LLM：结构化调用返回预置对象，自由调用返回固定章节文本。"""

    def __init__(self, structured_map: dict[type, Any], chapter_text: str) -> None:
        self._structured_map = structured_map
        self._chapter_text = chapter_text

    def with_structured_output(self, schema: type, **_: Any) -> _StructuredRunnable:
        return _StructuredRunnable(self._structured_map[schema])

    async def ainvoke(self, _prompt: Any, *args: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(content=self._chapter_text)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """创建一个含两个源码文件的样例项目目录。"""
    (tmp_path / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (tmp_path / "util.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    sub = tmp_path / "__pycache__"
    sub.mkdir()
    (sub / "junk.py").write_text("# should be skipped\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_llm() -> FakeWikiLLM:
    """两抽象、一关系、固定章节文本的假 LLM。"""
    structured_map = {
        IdentifyResult: IdentifyResult(
            abstractions=[
                Abstraction(name="Core", description="核心入口", file_indices=[0, 9]),
                Abstraction(name="Util", description="辅助函数", file_indices=[1]),
            ]
        ),
        RelationshipsResult: RelationshipsResult(
            summary="一个 **示例** 项目。",
            details=[Relationship(from_abstraction=0, to_abstraction=1, label="使用")],
        ),
        OrderResult: OrderResult(chapter_order=[1, 0]),
    }
    return FakeWikiLLM(structured_map, chapter_text="# 章节正文\n\n示例内容。")


@pytest.fixture
def patch_wiki_llm(
    monkeypatch: pytest.MonkeyPatch, fake_llm: FakeWikiLLM
) -> Iterator[FakeWikiLLM]:
    """把 wiki 节点里的 get_llm 替换成返回假 LLM。"""
    monkeypatch.setattr(
        "asukabot.core.graph.wiki.nodes.get_llm", lambda _model_id: fake_llm
    )
    yield fake_llm
