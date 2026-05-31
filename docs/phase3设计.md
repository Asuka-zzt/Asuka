# Phase 3 设计 — Wiki 生成工具（LangGraph 子图）

> 目标：用户对 Agent 说"给 /path/to/project 生成 wiki"，Agent 调用 `generate_wiki` 工具，
> 工具内部跑一条 **LangGraph `StateGraph` 流水线**，将代码库分析成一套 beginner-friendly 的
> Markdown 教程（`index.md` + 各章节页 + Mermaid 关系图）。
>
> 参考 `ref/Tutorial-Codebase-Knowledge`（PocketFlow 版的 codebase→tutorial pipeline），
> **用 LangGraph 重写其 Flow**。

---

## 1. 范围

**做：**
- 本地目录代码库 → 多文件收集（FetchRepo 的 local 分支）。
- 5 阶段 LLM 流水线：识别核心抽象 → 分析关系 → 排章节序 → 写各章 → 组装输出。
- 用 **LangGraph `StateGraph`** 编排，**`Send` API 并发写章节**。
- 把整条图 **封装成 LangChain `@tool`**，注入 Phase 2 的 `create_agent`，由对话 Agent 自主调用。
- `core/tools/registry.py` 工具注册表（按 Agent 分配工具）。

**不做（登记到 TODO）：**
- GitHub 远程仓库抓取（只做 local dir；`crawl_github_files` 等价物推迟）。
- 章节间"已写章节摘要"上下文传递（`Send` 并行写章，**牺牲跨章上下文**，见 §8）。
- LLM 响应缓存层（参考里的 `use_cache`）。
- 插件动态加载 / 工具沙箱（仍按既有 TODO，本阶段工具写死注册）。
- 多语言完整适配（保留 `language` 参数，默认中文，不做逐字段语言提示工程）。

---

## 2. 核心决策：为什么用 LangGraph 子图，而非单 `@tool`

`实现计划.md` 原计划是"单 `@tool wiki_generator`，内部顺序跑 7 步，不拆子图"。
本阶段**改为 LangGraph `StateGraph` 子图**，理由：

| 维度 | 单函数 @tool | LangGraph 子图（本设计） |
|---|---|---|
| 与 AGENTS.md 架构一致 | ✗ 业务塞进一个函数 | ✓ 落在 `core/graph/`，符合"LangGraph 编排"分层 |
| 并发 | 手写 `asyncio.gather` | ✓ 原生 `Send` fan-out，与未来多 Agent 并发同一套范式 |
| 状态 / 重试 / 可观测 | 自己管 | ✓ 节点级 state、`astream_events` 可观测、可加 checkpointer |
| 可测试性 | 整块难拆 | ✓ 每个节点是纯函数，单独可测 |
| 复用 Phase 2 经验 | — | ✓ 复用 `get_llm` / provider 层 |

**关键点**：`Send` 并发写章节，正是 AGENTS.md 里"多 Agent 并发（`StateGraph` + `Send`）"
要落地的同一机制——Phase 3 先用它跑通 wiki，为 Phase 后续多 Agent 调度铺路。

---

## 3. 参考映射：PocketFlow Flow → LangGraph StateGraph

参考 `flow.py` 是 6 个 `Node` 线性串联（`>>`），`WriteChapters` 是 `BatchNode`。
逐节点映射到 LangGraph：

| PocketFlow Node | LangGraph 节点 | LLM | 说明 |
|---|---|---|---|
| `FetchRepo` | `fetch_files` | ✗ | 遍历本地目录，收集 `(path, content)` 列表 |
| `IdentifyAbstractions` | `identify_abstractions` | 1 次 | 识别 top-N 核心抽象 |
| `AnalyzeRelationships` | `analyze_relationships` | 1 次 | 项目摘要 + 抽象间关系边 |
| `OrderChapters` | `order_chapters` | 1 次 | 决定章节教学顺序 |
| `WriteChapters`（BatchNode）| `write_chapter` ×N（**`Send` fan-out**）| N 次（并行）| 每个抽象写一章 |
| `CombineTutorial` | `combine_tutorial` | ✗ | 写 `index.md` + 各章 `.md` + Mermaid 图 |

**改进点**：参考用"LLM 输出 ```yaml``` → 手写解析 + 校验"。本设计改用
LangChain **`.with_structured_output(PydanticModel)`**，更稳、更类型安全，符合"禁用裸 dict"。

---

## 4. 新增文件与职责

```
asukabot/core/
├── graph/
│   └── wiki/                       # Wiki 生成子图（自成一包，隔离于未来 dispatch 图）
│       ├── __init__.py             build_wiki_graph() → 编译后的 StateGraph
│       ├── state.py                WikiState(TypedDict) + Pydantic 输出 schema
│       ├── nodes.py                节点纯函数：fetch_files / identify_abstractions / ...
│       ├── prompts.py              各阶段 prompt 模板（与节点逻辑解耦）
│       └── fs.py                   目录遍历 + 文件过滤 + 写盘（参考 crawl_local_files）
└── tools/
    ├── __init__.py
    ├── registry.py                 get_tools_for_agent(agent_id) → list[BaseTool]
    └── wiki_generator.py           @tool generate_wiki(...) 封装 build_wiki_graph().ainvoke()
```

**改动既有文件：**
- `core/graph/dispatch.py`：`create_agent(..., tools=get_tools_for_agent(cfg.id))` 注入工具。
- `config.py`：新增 `wiki_output_dir`、`wiki_max_file_size`、`wiki_max_abstractions` 等默认值。
- `pyproject.toml`：`uv add pyyaml`（仅当保留 YAML 兜底解析时；纯 structured_output 可不加）。

---

## 5. 状态与数据结构

### 5.1 `WikiState`（子图 state，TypedDict）

```python
import operator
from typing import Annotated, TypedDict

class WikiState(TypedDict):
    # —— 输入 ——
    project_path: str            # 本地代码目录绝对/相对路径
    project_name: str            # 由 path 末段派生或显式传入
    language: str                # 教程语言，默认 "chinese"
    output_dir: str              # 输出根目录，默认 settings.wiki_output_dir
    max_abstractions: int        # 抽象数量上限，默认 10

    # —— 中间产物 ——
    files: list[tuple[str, str]]                 # (相对路径, 内容)
    abstractions: list[dict]                     # {name, description, files: [int]}
    relationships: dict                          # {summary, details: [{from, to, label}]}
    chapter_order: list[int]                     # 抽象索引的有序列表

    # —— Send fan-out 汇聚（reducer 累加）——
    chapters: Annotated[list[dict], operator.add]  # [{chapter_num, content}]

    # —— 输出 ——
    final_output_dir: str
```

> `chapters` 用 `Annotated[..., operator.add]` 作 reducer：N 个并行 `write_chapter`
> 各返回 `{"chapters": [一章]}`，框架自动合并成完整列表（顺序不保证 → 每章带
> `chapter_num`，`combine_tutorial` 里按它排序）。

### 5.2 LLM 结构化输出 schema（Pydantic，给 `with_structured_output`）

```python
class Abstraction(BaseModel):
    name: str
    description: str            # ~100 字、含通俗类比
    file_indices: list[int]     # 相关文件在 files 列表中的下标

class IdentifyResult(BaseModel):
    abstractions: list[Abstraction]

class Relationship(BaseModel):
    from_abstraction: int
    to_abstraction: int
    label: str                  # 几个词，如 "Manages" / "Uses"

class RelationshipsResult(BaseModel):
    summary: str                # 项目整体摘要（markdown）
    details: list[Relationship]

class OrderResult(BaseModel):
    chapter_order: list[int]    # 抽象索引的教学顺序
```

`write_chapter` 输出是自由 Markdown 文本，不用结构化 schema（直接取 `.content`）。

---

## 6. 图结构与节点设计

### 6.1 拓扑

```
START
  → fetch_files
  → identify_abstractions
  → analyze_relationships
  → order_chapters
  → [conditional fan-out: 每个 chapter 一个 Send] → write_chapter (×N 并行)
  → combine_tutorial            （fan-in：等所有 write_chapter 完成）
  → END
```

```python
# core/graph/wiki/__init__.py
def build_wiki_graph():
    g = StateGraph(WikiState)
    g.add_node("fetch_files", fetch_files)
    g.add_node("identify_abstractions", identify_abstractions)
    g.add_node("analyze_relationships", analyze_relationships)
    g.add_node("order_chapters", order_chapters)
    g.add_node("write_chapter", write_chapter)
    g.add_node("combine_tutorial", combine_tutorial)

    g.add_edge(START, "fetch_files")
    g.add_edge("fetch_files", "identify_abstractions")
    g.add_edge("identify_abstractions", "analyze_relationships")
    g.add_edge("analyze_relationships", "order_chapters")
    g.add_conditional_edges("order_chapters", fan_out_chapters, ["write_chapter"])
    g.add_edge("write_chapter", "combine_tutorial")
    g.add_edge("combine_tutorial", END)
    return g.compile()
```

### 6.2 各节点（输入 → 输出）

**`fetch_files(state)`**（无 LLM）
- 遍历 `project_path`，按 include/exclude pattern + `max_file_size` 过滤（复用 `fs.py`，
  逻辑参考 `crawl_local_files`：跳过 `.git/__pycache__/node_modules/.venv` 等）。
- 返回 `{"files": [(rel_path, content), ...]}`；空则 raise `ValueError("未找到可分析文件")`。

**`identify_abstractions(state)`**（1 次 LLM，结构化）
- 把所有文件拼成带 `--- File Index i: path ---` 的 context（prompt 见 `prompts.py`）。
- `llm.with_structured_output(IdentifyResult)` → 校验 `file_indices` 落在 `[0, len(files))`。
- 返回 `{"abstractions": [{name, description, files:[int]}, ...]}`。

**`analyze_relationships(state)`**（1 次 LLM，结构化）
- 仅取被抽象引用到的文件片段 + 抽象清单作 context。
- `with_structured_output(RelationshipsResult)` → `{"relationships": {summary, details}}`。

**`order_chapters(state)`**（1 次 LLM，结构化）
- 输入抽象清单 + 关系，输出教学顺序。
- `with_structured_output(OrderResult)` → 校验是 `abstractions` 索引的合法全排列 →
  `{"chapter_order": [int]}`。

**`fan_out_chapters(state) -> list[Send]`**（路由函数，非节点）
```python
def fan_out_chapters(state: WikiState) -> list[Send]:
    order = state["chapter_order"]
    return [
        Send("write_chapter", {
            "chapter_num": i + 1,
            "abstraction_index": idx,
            "abstraction": state["abstractions"][idx],
            "files": state["files"],
            "project_name": state["project_name"],
            "language": state["language"],
            "full_chapter_listing": _listing(order, state["abstractions"]),
            "prev": _neighbor(order, i - 1, state["abstractions"]),
            "next": _neighbor(order, i + 1, state["abstractions"]),
        })
        for i, idx in enumerate(order)
    ]
```

**`write_chapter(payload)`**（1 次 LLM，自由文本，**并行实例**）
- 只读该抽象 `files` 下标对应的文件内容（context 有界，规避超长）。
- prompt 带：本章抽象名/描述 + 相关代码 + 全章目录（用于章间链接）+ 上一章/下一章导航。
- 返回 `{"chapters": [{"chapter_num": payload["chapter_num"], "content": md}]}`
  （reducer 累加）。

**`combine_tutorial(state)`**（无 LLM）
- `sorted(state["chapters"], key=lambda c: c["chapter_num"])` 还原顺序。
- 生成 Mermaid `flowchart TD`（节点=抽象名，边=relationship label，参考 `CombineTutorial`）。
- 组 `index.md`（摘要 + Mermaid + 章节链接）；每章写 `NN_safe_name.md`。
- 落盘到 `{output_dir}/{project_name}/`，返回 `{"final_output_dir": path}`。

---

## 7. 工具封装与接入对话 Agent

### 7.1 `@tool generate_wiki`

```python
# core/tools/wiki_generator.py
@tool
async def generate_wiki(project_path: str, language: str = "chinese") -> str:
    """为指定本地代码目录生成一套 Wiki 教程文档（index.md + 各章节 Markdown）。
    当用户要求"给某个项目/目录生成 wiki / 教程 / 文档"时调用本工具。
    参数 project_path 是本地目录路径；language 是教程语言（默认中文）。
    返回生成结果摘要（输出目录与文件清单）。
    """
    graph = build_wiki_graph()
    result = await graph.ainvoke({
        "project_path": project_path,
        "project_name": Path(project_path).resolve().name,
        "language": language,
        "output_dir": get_settings().wiki_output_dir,
        "max_abstractions": get_settings().wiki_max_abstractions,
    })
    out = result["final_output_dir"]
    n = len(result["chapters"])
    return f"已生成 Wiki：{out}（index.md + {n} 个章节页）"
```

> 子图 `build_wiki_graph()` 编译一次后可缓存（模块级单例，类比 `dispatch._agent`）。

### 7.2 注册表与注入

```python
# core/tools/registry.py
def get_tools_for_agent(agent_id: str) -> list[BaseTool]:
    return [generate_wiki]      # Phase 3 写死；插件系统就绪后改为动态发现

# core/graph/dispatch.py（改动）
_agent = create_agent(
    model=get_llm(cfg.model_id),
    tools=get_tools_for_agent(cfg.id),     # ← 由 [] 改为注入 wiki 工具
    system_prompt=cfg.soul,
    checkpointer=await get_checkpointer(),
)
```

`create_agent`（react agent）会自动处理"决定调用工具 → 执行 → 把结果喂回 LLM → 出最终答复"
的循环，**WebSocket 流式与 Phase 2 完全兼容**（工具执行期间无 token，执行后续流式总结）。

---

## 8. 关键设计权衡

| 决策 | 选择 | 理由 / 代价 |
|---|---|---|
| 章节写作并发 | **`Send` 并行** | 契合 LangGraph 范式、更快；**代价**：丢失参考里"已写章节摘要"跨章上下文。每章仍有全章目录 + 前后邻居导航，链接与过渡可用，连贯性可接受。需更强连贯时改"顺序 reduce 节点"。 |
| LLM 输出解析 | **`with_structured_output`** | 比手写 YAML 解析稳、类型安全；**风险**：DeepSeek 的 function-calling/json 模式兼容性需实测，故 `prompts.py` 保留 YAML 兜底说明，必要时降级。 |
| 数据源 | **仅 local dir** | 验收用 `ref/` 本地项目即可；GitHub 抓取登记 TODO。 |
| identify/analyze 上下文 | 整库 / 引用文件片段入单 prompt | 与参考一致，靠大上下文模型 + `max_file_size` 控制；**风险**：超大项目可能溢出，登记 TODO（后续可分批 map-reduce）。写章节阶段已天然有界。 |
| 子图 vs 主 dispatch 图 | wiki 独立成 `graph/wiki/` 子包 | 不污染未来多 Agent dispatch 图；工具边界清晰。 |

---

## 9. 数据流（端到端）

```
WS /ws/conv-1 ← {"message": "帮我给 ref/spec_agent/TradingAgents 生成 wiki"}
  → dispatch.build_agent()（带 generate_wiki 工具）
  → react agent: LLM 判定需调用 generate_wiki(project_path=..., language="chinese")
      → build_wiki_graph().ainvoke(WikiState)
          → fetch_files            收集源码文件
          → identify_abstractions  LLM → N 个核心抽象
          → analyze_relationships  LLM → 摘要 + 关系边
          → order_chapters         LLM → 章节顺序
          → Send ×N → write_chapter  并行 LLM 写每一章
          → combine_tutorial       写 index.md + NN_xx.md + Mermaid
      ← 工具返回："已生成 Wiki：output/TradingAgents（index.md + N 章）"
  → LLM 把工具结果转成自然语言答复 → astream_events 流式推送
  → {"type": "done"}
```

---

## 10. 测试方案

`tests/test_graph/test_wiki/` 与 `tests/test_tools/`，全程 `FakeListChatModel` mock，不发真实请求。

- **fetch_files**：临时目录造样例文件，断言过滤规则（跳过 `__pycache__`、超 `max_file_size`）。
- **identify / analyze / order**：用 `FakeListChatModel` 预置结构化返回，断言 state 字段与索引校验。
- **fan_out_chapters**：给定 `chapter_order`，断言 `Send` 数量与 payload（chapter_num、prev/next）。
- **write_chapter**：mock 返回固定 md，断言 `{"chapters": [{chapter_num, content}]}`。
- **combine_tutorial**：给定 chapters/relationships，断言 `index.md` 含 Mermaid 与全部章节链接，
  文件按序落盘。
- **端到端**：`build_wiki_graph().ainvoke(...)` 全 mock，断言 `final_output_dir` 下文件齐全。
- **工具接入**：断言 `get_tools_for_agent` 含 `generate_wiki`，agent 能触发 tool call（mock）。

验收口径：`uv run pytest` 全绿 + `ruff` 无 error + `mypy` 无 error。

---

## 11. 验收标准（真实 LLM 手动）

前置：`.env` 配 `DEEPSEEK_API_KEY`。

```
WS → "帮我给 ref/Tutorial-Codebase-Knowledge 生成 wiki 文档"
```

- ✓ Agent 正确识别意图并调用 `generate_wiki`。
- ✓ `output/<project>/` 下生成 `index.md`（含项目摘要 + Mermaid 关系图 + 章节导航）。
- ✓ 至少 3 个章节页内容准确反映对应模块。
- ✓ 多轮：追问"identify_abstractions 那一步是做什么的"，Agent 结合上下文作答。
- ✓ WebSocket 工具调用全程不崩，最终答复流式返回。

---

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| DeepSeek structured_output 兼容性 | 先 `utils/call_llm` 等价小脚本实测；`prompts.py` 留 YAML 兜底，必要时降级手解析 |
| identify/analyze 上下文溢出（大项目）| `max_file_size` + 文件数上限；登记 TODO，后续 map-reduce 分批 |
| `Send` 并行写章丢跨章上下文 | 每章带全章目录 + 前后邻居；连贯性不足时切顺序 reduce |
| 工具执行耗时长（N 次 LLM）| 并行 `Send` 已缓解；可加进度自定义事件（登记 TODO） |
| 写盘路径越权 | 限定 `output_dir` 在项目内，`project_path` 仅读不写 |

---

## 13. 登记到 `docs/todo/未完成功能.md` 的简化项（实现时补登）

- GitHub 远程抓取（只做 local dir）。
- 章节间"已写摘要"上下文（`Send` 并行牺牲）。
- LLM 响应缓存层。
- identify/analyze 大项目分批（map-reduce）。
- 工具进度事件下发（WebSocket 仅在工具结束后流式）。
- 工具仍写死注册（插件动态加载 / 沙箱按既有 TODO）。
```

