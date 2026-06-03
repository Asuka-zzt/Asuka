"""LangGraph 会话状态持久化：AsyncSqliteSaver 应用级单例。

多轮记忆完全交给 checkpointer，thread_id = conversation_id。
生命周期由 main.py 的 lifespan 管理（启动时 setup，关闭时释放）。
"""

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from asuka.config import get_settings

_cm: object | None = None
_saver: AsyncSqliteSaver | None = None


async def get_checkpointer() -> AsyncSqliteSaver:
    """返回全局单例 checkpointer，落盘 settings.session_db。"""
    global _cm, _saver
    if _saver is None:
        settings = get_settings()
        Path(settings.session_db).parent.mkdir(parents=True, exist_ok=True)
        _cm = AsyncSqliteSaver.from_conn_string(settings.session_db)
        _saver = await _cm.__aenter__()
    return _saver


async def close_checkpointer() -> None:
    """释放 checkpointer 连接（应用关闭时调用）。"""
    global _cm, _saver
    if _cm is not None:
        await _cm.__aexit__(None, None, None)  # type: ignore[attr-defined]
        _cm = None
        _saver = None
