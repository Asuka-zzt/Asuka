"""主调度图：构建可对话的 Agent。

Phase 2 用 LangGraph 预构建的 react agent（单 Agent，工具为空）。
Phase 3 起注入 core/tools 注册表中的工具（如 generate_wiki）。
后续阶段改为 StateGraph + Send 实现多 Agent 并发。
"""

from typing import Any

from langchain.agents import create_agent

from asukabot.api.provider import get_llm
from asukabot.core.agent.model import AgentConfig, default_agent
from asukabot.core.graph.checkpointer import get_checkpointer
from asukabot.core.tools import get_tools_for_agent

_agent: Any | None = None


async def build_agent(config: AgentConfig | None = None) -> Any:
    """构建（并缓存）默认 Agent 的 compiled graph。"""
    global _agent
    if _agent is None:
        cfg = config or default_agent()
        _agent = create_agent(
            model=get_llm(cfg.model_id),
            tools=get_tools_for_agent(cfg.id),
            system_prompt=cfg.soul,
            checkpointer=await get_checkpointer(),
        )
    return _agent
