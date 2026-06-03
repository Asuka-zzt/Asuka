"""主调度图：构建可对话的 Agent。

Phase 2 用 LangGraph 预构建的 react agent（单 Agent，工具为空）。
Phase 3 起注入 core/tools 注册表中的工具（如 generate_wiki）。
后续阶段改为 StateGraph + Send 实现多 Agent 并发。
"""

from typing import Any

from langchain.agents import create_agent

from asuka.api.provider import get_llm
from asuka.core.agent.model import AgentConfig, default_agent
from asuka.core.graph.checkpointer import get_checkpointer
from asuka.core.tools import get_tools_for_agent

_agents: dict[str, Any] = {}


def _cache_key(cfg: AgentConfig) -> str:
    """Agent 编译缓存 key。level 会进入 Soul，因此需要参与缓存。"""
    return f"{cfg.id}:{cfg.level or ''}:{cfg.model_id}"


async def build_agent(config: AgentConfig | None = None) -> Any:
    """构建（并缓存）指定 Agent 的 compiled graph。"""
    cfg = config or default_agent()
    key = _cache_key(cfg)
    if key not in _agents:
        _agents[key] = create_agent(
            model=get_llm(cfg.model_id),
            tools=get_tools_for_agent(cfg.id),
            system_prompt=cfg.soul,
            checkpointer=await get_checkpointer(),
        )
    return _agents[key]
