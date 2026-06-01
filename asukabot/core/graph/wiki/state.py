"""Wiki 生成子图的状态与 LLM 结构化输出 schema。

- WikiState：贯穿整条 StateGraph 的运行时状态（TypedDict）。
- Pydantic schema：交给 `llm.with_structured_output(...)`，规避手写 YAML 解析。
"""

import operator
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field


class Abstraction(BaseModel):
    """一个核心抽象（概念/模块）。"""

    name: str = Field(description="简洁的抽象名称")
    description: str = Field(description="约 100 字、含通俗类比的初学者友好描述")
    file_indices: list[int] = Field(
        default_factory=list,
        description="相关文件在 files 列表中的下标（整数）",
    )


class IdentifyResult(BaseModel):
    """identify_abstractions 节点的 LLM 输出。"""

    abstractions: list[Abstraction]


class Relationship(BaseModel):
    """抽象之间的一条关系边。"""

    from_abstraction: int = Field(description="源抽象的索引")
    to_abstraction: int = Field(description="目标抽象的索引")
    label: str = Field(description="关系标签，几个词，如 Manages / Uses")


class RelationshipsResult(BaseModel):
    """analyze_relationships 节点的 LLM 输出。"""

    summary: str = Field(description="项目整体功能摘要（markdown，初学者友好）")
    details: list[Relationship] = Field(default_factory=list)


class OrderResult(BaseModel):
    """order_chapters 节点的 LLM 输出。"""

    chapter_order: list[int] = Field(description="抽象索引按教学顺序排列")


class ChapterDraft(TypedDict):
    """单章草稿（write_chapter 的并行输出元素）。"""

    chapter_num: int
    content: str


class WikiState(TypedDict, total=False):
    """Wiki 生成子图的运行时状态。"""

    # —— 输入 ——
    project_path: str
    project_name: str
    language: str
    output_dir: str
    max_abstractions: int
    include_patterns: list[str]
    exclude_patterns: list[str]
    max_file_size: int

    # —— 中间产物 ——
    files: list[tuple[str, str]]  # (相对路径, 内容)
    abstractions: list[dict[str, Any]]  # {name, description, files: [int]}
    relationships: dict[str, Any]  # {summary, details: [{from, to, label}]}
    chapter_order: list[int]  # 抽象索引的有序列表

    # —— Send fan-out 汇聚（reducer 累加，顺序不保证 → 按 chapter_num 排序）——
    chapters: Annotated[list[ChapterDraft], operator.add]

    # —— 输出 ——
    final_output_dir: str
