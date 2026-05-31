"""Agent 配置 schema（静态结构）。"""

from pydantic import BaseModel, Field

from asukabot.config import get_settings


class AgentConfig(BaseModel):
    """单个 Agent 的配置。Phase 2 仅使用一个硬编码的 default agent。"""

    id: str = "default"
    name: str = "Asuka"
    soul: str = "你是 Asuka，一个友好、简洁、乐于助人的 AI 助手。"
    model_id: str = Field(default_factory=lambda: get_settings().default_model)


def default_agent() -> AgentConfig:
    """返回默认 Agent 配置。"""
    return AgentConfig()
