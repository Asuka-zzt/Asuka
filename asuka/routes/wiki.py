"""POST /generate_wiki — 独立触发 Codebase2Wiki 生成。"""

import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from asuka.config import get_settings
from asuka.core.graph.wiki import build_wiki_graph
from asuka.core.graph.wiki.fs import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_INCLUDE_PATTERNS,
)

router = APIRouter()


class GenerateWikiRequest(BaseModel):
    """Codebase2Wiki 表单请求，字段对齐参考 CLI。"""

    model_config = ConfigDict(populate_by_name=True)

    repo: str | None = None
    token: str | None = None
    local_dir: str | None = Field(default=None, alias="dir")
    name: str | None = None
    include: list[str] = Field(default_factory=lambda: sorted(DEFAULT_INCLUDE_PATTERNS))
    exclude: list[str] = Field(default_factory=lambda: sorted(DEFAULT_EXCLUDE_PATTERNS))
    max_size: int = Field(default=100_000, ge=1)
    output: str = "output"
    language: Literal["english", "chinese"] = "english"
    max_abstractions: int = Field(default=10, ge=1)
    no_cache: bool = False

    @model_validator(mode="after")
    def validate_source(self) -> "GenerateWikiRequest":
        """确保 GitHub repo 与本地目录二选一。"""
        has_repo = bool(self.repo and self.repo.strip())
        has_dir = bool(self.local_dir and self.local_dir.strip())
        if has_repo == has_dir:
            raise ValueError("repo 与 dir 必须且只能填写一个")
        return self


class WikiFile(BaseModel):
    """生成出的 Markdown 文件。"""

    path: str
    size: int
    content: str


class GenerateWikiResponse(BaseModel):
    """Codebase2Wiki 生成结果。"""

    status: Literal["success"]
    project_name: str
    output_dir: str
    files: list[WikiFile]
    chapter_order: list[int]


def _github_zip_url(repo_url: str) -> tuple[str, str]:
    """把 GitHub 仓库 URL 转换成 zipball API 地址，并返回推导项目名。"""
    parsed = urlparse(repo_url.strip())
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("目前仅支持 github.com 仓库 URL")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub 仓库 URL 格式应为 https://github.com/owner/repo")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    project_name = repo
    branch = parts[3] if len(parts) >= 4 and parts[2] == "tree" else None
    suffix = f"/{branch}" if branch else ""
    return f"https://api.github.com/repos/{owner}/{repo}/zipball{suffix}", project_name


def _download_github_repo(repo_url: str, token: str | None, target_root: Path) -> Path:
    """下载 GitHub zipball 到临时目录，返回解压后的项目根目录。"""
    zip_url, _ = _github_zip_url(repo_url)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Asuka-Codebase2Wiki",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(zip_url, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
    except URLError as exc:
        raise ValueError(f"下载 GitHub 仓库失败：{exc.reason}") from exc

    target_root.mkdir(parents=True, exist_ok=True)
    root_resolved = target_root.resolve()
    with ZipFile(BytesIO(payload)) as archive:
        for member in archive.infolist():
            destination = (target_root / member.filename).resolve()
            if root_resolved not in destination.parents and destination != root_resolved:
                raise ValueError("GitHub 压缩包包含不安全路径")
            archive.extract(member, target_root)

    dirs = sorted(path for path in target_root.iterdir() if path.is_dir())
    if not dirs:
        raise ValueError("GitHub 压缩包中没有可分析目录")
    return dirs[0]


def _infer_project_name(req: GenerateWikiRequest, project_path: Path) -> str:
    """从请求或输入路径推导项目名。"""
    if req.name and req.name.strip():
        return req.name.strip()
    if req.repo:
        _, repo_name = _github_zip_url(req.repo)
        return repo_name
    return project_path.resolve().name


def _generated_files(output_dir: Path) -> list[WikiFile]:
    """列出生成目录中的 Markdown 文件。"""
    if not output_dir.exists():
        return []
    files: list[WikiFile] = []
    for path in sorted(output_dir.rglob("*.md")):
        if path.is_file():
            files.append(
                WikiFile(
                    path=path.relative_to(output_dir).as_posix(),
                    size=path.stat().st_size,
                    content=path.read_text(encoding="utf-8"),
                )
            )
    return files


@router.post("/generate_wiki", response_model=GenerateWikiResponse)
async def generate_wiki(req: GenerateWikiRequest) -> GenerateWikiResponse:
    """运行 Wiki 子图，返回输出目录与文件列表。"""
    settings = get_settings()
    output = req.output.strip() or settings.wiki_output_dir

    try:
        with TemporaryDirectory(prefix="asuka-wiki-") as temp_dir:
            if req.repo:
                project_path = await asyncio.to_thread(
                    _download_github_repo,
                    req.repo,
                    req.token,
                    Path(temp_dir) / "repo",
                )
            else:
                assert req.local_dir is not None
                project_path = Path(req.local_dir).expanduser()

            project_name = _infer_project_name(req, project_path)
            graph = build_wiki_graph()
            result = await graph.ainvoke(
                {
                    "project_path": str(project_path),
                    "project_name": project_name,
                    "language": req.language,
                    "output_dir": output,
                    "max_abstractions": req.max_abstractions,
                    "include_patterns": req.include,
                    "exclude_patterns": req.exclude,
                    "max_file_size": req.max_size,
                }
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    final_output_dir = Path(result["final_output_dir"])
    return GenerateWikiResponse(
        status="success",
        project_name=project_name,
        output_dir=str(final_output_dir),
        files=_generated_files(final_output_dir),
        chapter_order=list(result.get("chapter_order", [])),
    )
