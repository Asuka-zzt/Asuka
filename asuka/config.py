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
    default_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # 数据
    data_dir: str = "./data"
    session_db: str = "./data/sessions.db"

    # Wiki 生成工具
    wiki_output_dir: str = "./output"
    wiki_max_file_size: int = 100_000  # 单文件字节上限，超出跳过
    wiki_max_abstractions: int = 10  # 识别核心抽象数量上限

    # TTS
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_voices: dict[str, str] = {
        "english": "en-US-AriaNeural",
        "japanese": "ja-JP-NanamiNeural",
    }
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"
    tts_pitch: str = "+0Hz"
    tts_max_chars: int = 1200


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（带缓存）。"""
    return Settings()
