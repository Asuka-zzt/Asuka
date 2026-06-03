"""generate_wiki 工具：把 Wiki 生成子图封装成对话 Agent 可调用的 LangChain @tool。"""

from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from asuka.config import get_settings
from asuka.core.graph.wiki import build_wiki_graph


@tool
async def generate_wiki(project_path: str, language: str = "chinese") -> str:
    """为指定本地代码目录生成一套 Wiki 教程文档（index.md + 各章节 Markdown）。

    当用户要求“给某个项目/目录生成 wiki / 教程 / 文档”时调用本工具。

    Args:
        project_path: 本地代码目录路径。
        language: 教程语言，默认中文。

    Returns:
        生成结果摘要（输出目录与章节数）。
    """
    settings = get_settings()
    graph = build_wiki_graph()
    state: dict[str, Any] = {
        "project_path": project_path,
        "project_name": Path(project_path).resolve().name,
        "language": language,
        "output_dir": settings.wiki_output_dir,
        "max_abstractions": settings.wiki_max_abstractions,
    }
    result = await graph.ainvoke(state)
    out = result["final_output_dir"]
    n = len(result.get("chapters", []))
    return f"已生成 Wiki：{out}（index.md + {n} 个章节页）"
