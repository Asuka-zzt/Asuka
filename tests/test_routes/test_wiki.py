"""Codebase2Wiki REST 路由。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from asukabot.routes import wiki
from tests.conftest import FakeWikiLLM


@pytest.fixture
def wiki_app() -> Iterator[FastAPI]:
    """构建仅含 wiki 路由的测试 app。"""
    app = FastAPI()
    app.include_router(wiki.router)
    yield app


def test_generate_wiki_route_local_dir(
    wiki_app: FastAPI,
    patch_wiki_llm: FakeWikiLLM,
    sample_project: Path,
    tmp_path: Path,
) -> None:
    client = TestClient(wiki_app)

    response = client.post(
        "/generate_wiki",
        json={
            "dir": str(sample_project),
            "name": "demo",
            "include": ["*.py"],
            "exclude": ["test_*"],
            "max_size": 100_000,
            "output": str(tmp_path / "wiki_out"),
            "language": "chinese",
            "max_abstractions": 2,
            "no_cache": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["project_name"] == "demo"
    assert payload["output_dir"] == str(tmp_path / "wiki_out" / "demo")
    assert payload["chapter_order"] == [1, 0]
    assert {item["path"] for item in payload["files"]} == {
        "index.md",
        "01_util.md",
        "02_core.md",
    }
    assert all(isinstance(item["content"], str) and item["content"] for item in payload["files"])


def test_generate_wiki_route_requires_one_source(wiki_app: FastAPI) -> None:
    client = TestClient(wiki_app)
    response = client.post(
        "/generate_wiki",
        json={
            "repo": "https://github.com/example/repo",
            "dir": "/tmp/repo",
        },
    )
    assert response.status_code == 422
