"""Wiki 子图的文件系统辅助：本地目录遍历（收集源码）与结果落盘。

参考 ref/Tutorial-Codebase-Knowledge/utils/crawl_local_files.py，
简化为纯 fnmatch 过滤，不引入 pathspec 依赖。
"""

import fnmatch
import os
from pathlib import Path

DEFAULT_INCLUDE_PATTERNS: set[str] = {
    "*.py", "*.pyi", "*.js", "*.jsx", "*.ts", "*.tsx", "*.go", "*.java",
    "*.c", "*.cc", "*.cpp", "*.h", "*.rs", "*.rb", "*.php",
    "*.md", "*.rst", "*.yaml", "*.yml", "*.toml",
    "Dockerfile", "Makefile",
}

DEFAULT_EXCLUDE_DIRS: set[str] = {
    ".git", ".github", ".venv", "venv", "node_modules",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".next", "output", "tests",
}

DEFAULT_EXCLUDE_PATTERNS: set[str] = {"*.lock", "*.log", "*_test.*", "test_*"}


def _matches_any(rel_path: str, patterns: set[str]) -> bool:
    """rel_path 或其 basename 命中任一 glob 模式。"""
    name = os.path.basename(rel_path)
    return any(
        fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(name, p) for p in patterns
    )


def collect_files(
    directory: str,
    include_patterns: set[str] | None = None,
    exclude_patterns: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_file_size: int = 100_000,
) -> list[tuple[str, str]]:
    """遍历本地目录，收集 (相对路径, 内容) 列表。

    跳过：被排除目录下的文件、不匹配 include、命中 exclude、超过 max_file_size、
    无法以 UTF-8 解码的文件。
    """
    base = Path(directory)
    if not base.is_dir():
        raise ValueError(f"目录不存在：{directory}")

    include = include_patterns or DEFAULT_INCLUDE_PATTERNS
    exclude = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
    skip_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS

    collected: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(base):
        # 提前剪掉被排除的目录（按目录名），避免深入遍历
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for filename in files:
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, base)
            if not _matches_any(rel_path, include):
                continue
            if _matches_any(rel_path, exclude):
                continue
            try:
                if os.path.getsize(abs_path) > max_file_size:
                    continue
                with open(abs_path, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            collected.append((rel_path.replace(os.sep, "/"), content))

    collected.sort(key=lambda item: item[0])
    return collected


def write_wiki(
    output_path: str,
    index_content: str,
    chapter_files: list[dict[str, str]],
) -> str:
    """写 index.md 与各章节文件到 output_path，返回该目录路径。"""
    out = Path(output_path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.md").write_text(index_content, encoding="utf-8")
    for chapter in chapter_files:
        (out / chapter["filename"]).write_text(chapter["content"], encoding="utf-8")
    return str(out)
