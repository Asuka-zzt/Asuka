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

    # Realtime voice ASR
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    # Realtime voice VAD
    voice_vad_rms_threshold: float = 0.012
    voice_vad_min_speech_ms: int = 300
    voice_vad_silence_ms: int = 700
    voice_vad_max_speech_ms: int = 20_000

    # Realtime voice Piper TTS
    realtime_tts_provider: str = "piper"
    piper_model_by_language: dict[str, str] = {}
    piper_sample_rate: int = 48_000

    # Realtime voice Qwen3-TTS via DashScope
    dashscope_api_key: str = ""
    qwen_tts_base_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
        "multimodal-generation/generation"
    )
    qwen_tts_model: str = "qwen3-tts-flash"
    qwen_tts_voice: str = "Cherry"
    qwen_tts_timeout_seconds: float = 30.0
    qwen_tts_language_type_by_language: dict[str, str] = {
        "chinese": "Chinese",
        "english": "English",
        "japanese": "Japanese",
    }

    # Realtime voice Volcengine TTS
    volcengine_tts_base_url: str = (
        "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
    )
    volcengine_tts_api_key: str = ""
    volcengine_tts_app_id: str = ""
    volcengine_tts_access_key: str = ""
    volcengine_tts_resource_id: str = "seed-tts-2.0"
    volcengine_tts_voice_type: str = "zh_female_vv_uranus_bigtts"
    volcengine_tts_encoding: str = "pcm"
    # Match the WebRTC output track rate so realtime audio needs no resampling
    # (per-segment resampling adds boundary clicks). Volcengine supports 48 kHz.
    volcengine_tts_sample_rate: int = 48_000
    volcengine_api_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（带缓存）。"""
    return Settings()
