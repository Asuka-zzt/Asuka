"""全局配置：通过 pydantic-settings 从环境变量 / .env 读取。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用级配置。所有敏感信息只从环境变量读取，禁止硬编码。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # 默认 LLM
    default_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # 数据
    data_dir: str = "./data"
    session_db: str = "./data/sessions.db"


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（带缓存）。"""
    return Settings()
