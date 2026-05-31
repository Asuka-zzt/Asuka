"""Wiki 生成子图：将本地代码库分析成一套 Markdown 教程。

build_wiki_graph() 编译一条 StateGraph 流水线：
fetch_files → identify_abstractions → analyze_relationships → order_chapters
→ [Send fan-out] write_chapter ×N → combine_tutorial
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from asukabot.core.graph.wiki.nodes import (
    analyze_relationships,
    combine_tutorial,
    fan_out_chapters,
    fetch_files,
    identify_abstractions,
    order_chapters,
    write_chapter,
)
from asukabot.core.graph.wiki.state import WikiState

_graph: Any | None = None


def build_wiki_graph() -> Any:
    """编译（并缓存）Wiki 生成子图。"""
    global _graph
    if _graph is None:
        g = StateGraph(WikiState)
        g.add_node("fetch_files", fetch_files)
        g.add_node("identify_abstractions", identify_abstractions)
        g.add_node("analyze_relationships", analyze_relationships)
        g.add_node("order_chapters", order_chapters)
        # write_chapter 接收 Send 派发的 payload（非 WikiState），故忽略类型检查
        g.add_node("write_chapter", write_chapter)  # type: ignore[arg-type]
        g.add_node("combine_tutorial", combine_tutorial)

        g.add_edge(START, "fetch_files")
        g.add_edge("fetch_files", "identify_abstractions")
        g.add_edge("identify_abstractions", "analyze_relationships")
        g.add_edge("analyze_relationships", "order_chapters")
        g.add_conditional_edges("order_chapters", fan_out_chapters, ["write_chapter"])
        g.add_edge("write_chapter", "combine_tutorial")
        g.add_edge("combine_tutorial", END)
        _graph = g.compile()
    return _graph


__all__ = ["build_wiki_graph"]
