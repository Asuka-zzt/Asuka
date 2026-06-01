"""Wiki 生成子图的节点函数（纯函数，便于单测）。

映射自 ref/Tutorial-Codebase-Knowledge 的 6 个 PocketFlow Node：
fetch_files / identify_abstractions / analyze_relationships /
order_chapters / write_chapter（Send 并发）/ combine_tutorial。
"""

from pathlib import Path
from typing import Any

from langgraph.types import Send

from asukabot.api.provider import get_llm
from asukabot.config import get_settings
from asukabot.core.graph.wiki import prompts
from asukabot.core.graph.wiki.fs import collect_files, write_wiki
from asukabot.core.graph.wiki.state import (
    ChapterDraft,
    IdentifyResult,
    OrderResult,
    RelationshipsResult,
    WikiState,
)


def _wiki_llm() -> Any:
    """Wiki 流水线使用的 LLM（默认模型）。"""
    return get_llm(get_settings().default_model)


def _structured(schema: type) -> Any:
    """结构化输出 Runnable。

    用 function_calling（工具调用）而非默认的 json_schema response_format：
    DeepSeek 不支持 json_schema response_format，但支持工具调用；
    该方式对 OpenAI / Anthropic 同样可用，最具可移植性。
    """
    return _wiki_llm().with_structured_output(schema, method="function_calling")


def _build_context(files: list[tuple[str, str]]) -> str:
    """把全部文件拼成带索引的上下文字符串。"""
    return "".join(
        f"--- File Index {i}: {path} ---\n{content}\n\n"
        for i, (path, content) in enumerate(files)
    )


def _file_listing(files: list[tuple[str, str]]) -> str:
    """文件索引清单：`- i # path`。"""
    return "\n".join(f"- {i} # {path}" for i, (path, _) in enumerate(files))


def _content_for_indices(
    files: list[tuple[str, str]], indices: list[int]
) -> dict[str, str]:
    """取指定下标文件的内容，key 为 `i # path`。"""
    result: dict[str, str] = {}
    for i in indices:
        if 0 <= i < len(files):
            path, content = files[i]
            result[f"{i} # {path}"] = content
    return result


def _safe_filename(chapter_num: int, name: str) -> str:
    """生成安全的章节文件名，如 `01_query_processing.md`。"""
    safe = "".join(c if c.isalnum() else "_" for c in name).lower().strip("_")
    return f"{chapter_num:02d}_{safe or 'chapter'}.md"


async def fetch_files(state: WikiState) -> dict[str, Any]:
    """遍历本地目录，收集源码文件。"""
    files = collect_files(
        state["project_path"],
        include_patterns=set(state["include_patterns"])
        if state.get("include_patterns")
        else None,
        exclude_patterns=set(state["exclude_patterns"])
        if state.get("exclude_patterns")
        else None,
        max_file_size=state.get("max_file_size", get_settings().wiki_max_file_size),
    )
    if not files:
        raise ValueError(f"未在 {state['project_path']} 找到可分析的文件")
    return {"files": files}


async def identify_abstractions(state: WikiState) -> dict[str, Any]:
    """LLM 识别 top-N 核心抽象。"""
    files = state["files"]
    prompt = prompts.identify_prompt(
        project_name=state["project_name"],
        context=_build_context(files),
        file_listing=_file_listing(files),
        max_abstractions=state.get("max_abstractions", 10),
        language=state.get("language", "chinese"),
    )
    result: IdentifyResult = await _structured(IdentifyResult).ainvoke(prompt)

    abstractions: list[dict[str, Any]] = []
    for abstr in result.abstractions:
        valid = sorted({i for i in abstr.file_indices if 0 <= i < len(files)})
        abstractions.append(
            {"name": abstr.name, "description": abstr.description, "files": valid}
        )
    if not abstractions:
        raise ValueError("LLM 未识别出任何抽象")
    return {"abstractions": abstractions}


async def analyze_relationships(state: WikiState) -> dict[str, Any]:
    """LLM 分析抽象间关系 + 生成项目摘要。"""
    files = state["files"]
    abstractions = state["abstractions"]

    listing = "\n".join(f"{i} # {a['name']}" for i, a in enumerate(abstractions))
    relevant: set[int] = set()
    info_lines = []
    for i, a in enumerate(abstractions):
        relevant.update(a["files"])
        idx_str = ", ".join(map(str, a["files"]))
        info_lines.append(
            f"- 索引 {i}: {a['name']}（相关文件下标: [{idx_str}]）\n  描述: {a['description']}"
        )
    snippets = _content_for_indices(files, sorted(relevant))
    context = (
        "已识别的抽象:\n"
        + "\n".join(info_lines)
        + "\n\n相关文件片段:\n"
        + "\n\n".join(f"--- File: {k} ---\n{v}" for k, v in snippets.items())
    )

    prompt = prompts.analyze_prompt(
        project_name=state["project_name"],
        abstraction_listing=listing,
        context=context,
        language=state.get("language", "chinese"),
    )
    result: RelationshipsResult = await _structured(RelationshipsResult).ainvoke(prompt)

    n = len(abstractions)
    details = [
        {"from": r.from_abstraction, "to": r.to_abstraction, "label": r.label}
        for r in result.details
        if 0 <= r.from_abstraction < n and 0 <= r.to_abstraction < n
    ]
    return {"relationships": {"summary": result.summary, "details": details}}


async def order_chapters(state: WikiState) -> dict[str, Any]:
    """LLM 决定章节教学顺序。"""
    abstractions = state["abstractions"]
    listing = "\n".join(f"{i} # {a['name']}" for i, a in enumerate(abstractions))

    prompt = prompts.order_prompt(
        project_name=state["project_name"],
        abstraction_listing=listing,
        relationships_summary=state["relationships"]["summary"],
        language=state.get("language", "chinese"),
    )
    result: OrderResult = await _structured(OrderResult).ainvoke(prompt)

    n = len(abstractions)
    # 去重并补全：保证每个抽象索引恰好出现一次
    order: list[int] = []
    seen: set[int] = set()
    for i in result.chapter_order:
        if 0 <= i < n and i not in seen:
            order.append(i)
            seen.add(i)
    for i in range(n):
        if i not in seen:
            order.append(i)
    return {"chapter_order": order}


def _chapter_label(order: list[int], pos: int, abstractions: list[dict[str, Any]]) -> str:
    """某位置章节的链接文本，如 `第 2 章 [名称](02_xxx.md)`。"""
    if not 0 <= pos < len(order):
        return ""
    idx = order[pos]
    name = abstractions[idx]["name"]
    return f"第 {pos + 1} 章 [{name}]({_safe_filename(pos + 1, name)})"


def fan_out_chapters(state: WikiState) -> list[Send]:
    """为每个章节派发一个并行 write_chapter（Send fan-out）。"""
    order = state["chapter_order"]
    abstractions = state["abstractions"]
    files = state["files"]
    full_listing = "\n".join(
        _chapter_label(order, pos, abstractions) for pos in range(len(order))
    )
    sends: list[Send] = []
    for pos, idx in enumerate(order):
        abstr = abstractions[idx]
        sends.append(
            Send(
                "write_chapter",
                {
                    "chapter_num": pos + 1,
                    "abstraction": abstr,
                    "file_context": _content_for_indices(files, abstr["files"]),
                    "project_name": state["project_name"],
                    "language": state.get("language", "chinese"),
                    "full_chapter_listing": full_listing,
                    "prev_chapter": _chapter_label(order, pos - 1, abstractions),
                    "next_chapter": _chapter_label(order, pos + 1, abstractions),
                },
            )
        )
    return sends


async def write_chapter(payload: dict[str, Any]) -> dict[str, list[ChapterDraft]]:
    """撰写单个章节（并行实例）。"""
    abstr = payload["abstraction"]
    file_context = "\n\n".join(
        f"--- File: {k.split('# ')[-1]} ---\n{v}"
        for k, v in payload["file_context"].items()
    )
    prompt = prompts.chapter_prompt(
        project_name=payload["project_name"],
        chapter_num=payload["chapter_num"],
        abstraction_name=abstr["name"],
        abstraction_description=abstr["description"],
        file_context=file_context,
        full_chapter_listing=payload["full_chapter_listing"],
        prev_chapter=payload["prev_chapter"],
        next_chapter=payload["next_chapter"],
        language=payload["language"],
    )
    response = await _wiki_llm().ainvoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    draft: ChapterDraft = {"chapter_num": payload["chapter_num"], "content": content}
    return {"chapters": [draft]}


def _mermaid(abstractions: list[dict[str, Any]], details: list[dict[str, Any]]) -> str:
    """生成 Mermaid flowchart。"""
    lines = ["flowchart TD"]
    for i, a in enumerate(abstractions):
        lines.append(f'    A{i}["{a["name"].replace(chr(34), "")}"]')
    for rel in details:
        label = rel["label"].replace('"', "").replace("\n", " ")[:30]
        lines.append(f'    A{rel["from"]} -- "{label}" --> A{rel["to"]}')
    return "\n".join(lines)


def combine_tutorial(state: WikiState) -> dict[str, Any]:
    """汇聚各章节，写 index.md + 章节文件 + Mermaid 图。"""
    abstractions = state["abstractions"]
    order = state["chapter_order"]
    relationships = state["relationships"]
    drafts = {c["chapter_num"]: c["content"] for c in state.get("chapters", [])}

    attribution = "\n\n---\n\n由 AsukaBot Wiki 生成器自动生成"

    index = f"# 教程：{state['project_name']}\n\n{relationships['summary']}\n\n"
    index += "```mermaid\n" + _mermaid(abstractions, relationships["details"]) + "\n```\n\n"
    index += "## 章节\n\n"

    chapter_files: list[dict[str, str]] = []
    for pos, idx in enumerate(order):
        chapter_num = pos + 1
        name = abstractions[idx]["name"]
        filename = _safe_filename(chapter_num, name)
        index += f"{chapter_num}. [{name}]({filename})\n"
        content = drafts.get(chapter_num, f"# 第 {chapter_num} 章：{name}\n\n（内容缺失）")
        chapter_files.append({"filename": filename, "content": content + attribution})
    index += attribution

    output_path = str(Path(state["output_dir"]) / state["project_name"])
    final_dir = write_wiki(output_path, index, chapter_files)
    return {"final_output_dir": final_dir}
