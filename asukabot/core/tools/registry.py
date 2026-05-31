"""工具注册表：按 Agent 分配可用工具。

Phase 3 写死注册 generate_wiki；插件系统就绪后改为动态发现 / 按配置分配。
"""

from langchain_core.tools import BaseTool

from asukabot.core.tools.wiki_generator import generate_wiki

_ALL_TOOLS: list[BaseTool] = [generate_wiki]


def get_tools_for_agent(agent_id: str) -> list[BaseTool]:
    """返回指定 Agent 可用的工具列表。"""
    return list(_ALL_TOOLS)
