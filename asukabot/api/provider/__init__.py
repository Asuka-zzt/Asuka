"""LLM Provider 适配层：按 model_id 路由到对应 LangChain ChatModel。"""

from langchain_core.language_models.chat_models import BaseChatModel

from asukabot.config import get_settings


def get_llm(model_id: str) -> BaseChatModel:
    """按 model_id 前缀路由到对应 provider 适配器。

    - deepseek-*  → ChatOpenAI（DeepSeek OpenAI 兼容接口）
    - gpt-*       → ChatOpenAI
    - claude-*    → ChatAnthropic
    """
    settings = get_settings()

    if model_id.startswith("deepseek"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_id,
            api_key=settings.deepseek_api_key,  # type: ignore[arg-type]
            base_url=settings.deepseek_base_url,
            streaming=True,
        )

    if model_id.startswith("gpt"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
            streaming=True,
        )

    if model_id.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_id,  # type: ignore[call-arg]
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
            streaming=True,
        )

    raise ValueError(f"未知的 model_id：{model_id}")
