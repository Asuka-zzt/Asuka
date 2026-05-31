"""端到端：build_wiki_graph 全流程（假 LLM）。"""

from pathlib import Path

from asukabot.core.graph.wiki import build_wiki_graph
from tests.conftest import FakeWikiLLM


async def test_wiki_graph_end_to_end(
    patch_wiki_llm: FakeWikiLLM, sample_project: Path
) -> None:
    out_dir = sample_project / "wiki_out"
    graph = build_wiki_graph()
    result = await graph.ainvoke(
        {
            "project_path": str(sample_project),
            "project_name": "demo",
            "language": "chinese",
            "output_dir": str(out_dir),
            "max_abstractions": 10,
        }
    )
    final = Path(result["final_output_dir"])
    assert final == out_dir / "demo"
    assert (final / "index.md").exists()
    # 两个抽象 → 两章
    assert len(result["chapters"]) == 2
    assert (final / "01_util.md").exists()
    assert (final / "02_core.md").exists()
    index = (final / "index.md").read_text(encoding="utf-8")
    assert "# 教程：demo" in index
    assert "```mermaid" in index
