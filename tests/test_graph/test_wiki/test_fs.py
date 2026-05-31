"""fs.py：目录遍历与落盘。"""

from pathlib import Path

import pytest

from asukabot.core.graph.wiki.fs import collect_files, write_wiki


def test_collect_files_filters(sample_project: Path) -> None:
    files = collect_files(str(sample_project))
    paths = {p for p, _ in files}
    assert paths == {"core.py", "util.py"}  # __pycache__ 被跳过


def test_collect_files_max_size(sample_project: Path) -> None:
    files = collect_files(str(sample_project), max_file_size=1)
    assert files == []  # 全部超过 1 字节，被跳过


def test_collect_files_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        collect_files(str(tmp_path / "nope"))


def test_write_wiki(tmp_path: Path) -> None:
    out = write_wiki(
        str(tmp_path / "proj"),
        "# index",
        [{"filename": "01_a.md", "content": "chapter a"}],
    )
    assert (Path(out) / "index.md").read_text(encoding="utf-8") == "# index"
    assert (Path(out) / "01_a.md").read_text(encoding="utf-8") == "chapter a"
