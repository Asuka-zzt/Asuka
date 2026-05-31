"""FastAPI 应用入口。

启动：uv run python -m asukabot.main
"""

from fastapi import FastAPI

from asukabot import __version__
from asukabot.config import get_settings


def create_app() -> FastAPI:
    """构建并返回 FastAPI 应用。"""
    app = FastAPI(title="AsukaBot", version=__version__)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

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
