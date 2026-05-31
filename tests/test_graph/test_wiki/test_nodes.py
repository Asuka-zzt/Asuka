"""wiki 节点函数：逐个验证 state 变换与 Send fan-out。"""

from pathlib import Path

import pytest

from asukabot.core.graph.wiki import nodes
from asukabot.core.graph.wiki.state import WikiState
from tests.conftest import FakeWikiLLM

FILES = [("core.py", "def run(): ..."), ("util.py", "def helper(): ...")]


def _base_state(project: Path) -> WikiState:
    return {
        "project_path": str(project),
        "project_name": "demo",
        "language": "chinese",
        "output_dir": str(project / "out"),
        "max_abstractions": 10,
    }


async def test_fetch_files(sample_project: Path) -> None:
    out = await nodes.fetch_files(_base_state(sample_project))
    assert {p for p, _ in out["files"]} == {"core.py", "util.py"}


async def test_fetch_files_empty(tmp_path: Path) -> None:
    state = _base_state(tmp_path)
    with pytest.raises(ValueError):
        await nodes.fetch_files(state)


async def test_identify_clamps_indices(
    patch_wiki_llm: FakeWikiLLM, sample_project: Path
) -> None:
    state = _base_state(sample_project)
    state["files"] = FILES
    out = await nodes.identify_abstractions(state)
    abstractions = out["abstractions"]
    assert [a["name"] for a in abstractions] == ["Core", "Util"]
    # file_indices 含越界的 9，应被裁掉
    assert abstractions[0]["files"] == [0]


async def test_analyze_filters_relationships(
    patch_wiki_llm: FakeWikiLLM, sample_project: Path
) -> None:
    state = _base_state(sample_project)
    state["files"] = FILES
    state["abstractions"] = [
        {"name": "Core", "description": "d", "files": [0]},
        {"name": "Util", "description": "d", "files": [1]},
    ]
    out = await nodes.analyze_relationships(state)
    rel = out["relationships"]
    assert rel["summary"].startswith("一个")
    assert rel["details"] == [{"from": 0, "to": 1, "label": "使用"}]


async def test_order_completes_missing(
    patch_wiki_llm: FakeWikiLLM, sample_project: Path
) -> None:
    state = _base_state(sample_project)
    state["abstractions"] = [
        {"name": "Core", "description": "d", "files": [0]},
        {"name": "Util", "description": "d", "files": [1]},
    ]
    state["relationships"] = {"summary": "s", "details": []}
    out = await nodes.order_chapters(state)
    assert sorted(out["chapter_order"]) == [0, 1]
    assert out["chapter_order"] == [1, 0]  # 来自假 LLM


def test_fan_out_chapters() -> None:
    state: WikiState = {
        "abstractions": [
            {"name": "Core", "description": "d", "files": [0]},
            {"name": "Util", "description": "d", "files": [1]},
        ],
        "chapter_order": [1, 0],
        "files": FILES,
        "project_name": "demo",
        "language": "chinese",
    }
    sends = nodes.fan_out_chapters(state)
    assert len(sends) == 2
    first = sends[0].arg
    assert first["chapter_num"] == 1
    assert first["abstraction"]["name"] == "Util"
    assert first["prev_chapter"] == ""  # 第一章无上一章
    assert "第 2 章" in first["next_chapter"]


async def test_write_chapter(patch_wiki_llm: FakeWikiLLM) -> None:
    payload = {
        "chapter_num": 1,
        "abstraction": {"name": "Util", "description": "d", "files": [1]},
        "file_context": {"1 # util.py": "def helper(): ..."},
        "project_name": "demo",
        "language": "chinese",
        "full_chapter_listing": "...",
        "prev_chapter": "",
        "next_chapter": "",
    }
    out = await nodes.write_chapter(payload)
    assert out["chapters"][0]["chapter_num"] == 1
    assert "章节正文" in out["chapters"][0]["content"]


def test_combine_tutorial(tmp_path: Path) -> None:
    state: WikiState = {
        "project_name": "demo",
        "output_dir": str(tmp_path),
        "abstractions": [
            {"name": "Core", "description": "d", "files": [0]},
            {"name": "Util", "description": "d", "files": [1]},
        ],
        "chapter_order": [1, 0],
        "relationships": {
            "summary": "摘要",
            "details": [{"from": 0, "to": 1, "label": "使用"}],
        },
        "chapters": [
            {"chapter_num": 2, "content": "# Core 章"},
            {"chapter_num": 1, "content": "# Util 章"},
        ],
    }
    out = nodes.combine_tutorial(state)
    out_dir = Path(out["final_output_dir"])
    index = (out_dir / "index.md").read_text(encoding="utf-8")
    assert "```mermaid" in index
    assert "1. [Util](01_util.md)" in index
    assert "2. [Core](02_core.md)" in index
    # 章节按 chapter_num 正确落盘
    assert (out_dir / "01_util.md").read_text(encoding="utf-8").startswith("# Util 章")
    assert (out_dir / "02_core.md").read_text(encoding="utf-8").startswith("# Core 章")
