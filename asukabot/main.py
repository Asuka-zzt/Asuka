"""FastAPI 应用入口。

启动：uv run python -m asukabot.main
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from asukabot import __version__
from asukabot.config import get_settings
from asukabot.core.graph.checkpointer import close_checkpointer
from asukabot.routes import chat, tts, wiki, ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：关闭时释放 checkpointer 连接。"""
    yield
    await close_checkpointer()


def create_app() -> FastAPI:
    """构建并返回 FastAPI 应用。"""
    app = FastAPI(title="AsukaBot", version=__version__, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(chat.router)
    app.include_router(tts.router)
    app.include_router(wiki.router)
    app.include_router(ws.router)
    return app


app = create_app()


def main() -> None:
    """以开发模式启动 uvicorn 服务。"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "asukabot.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
