# AGENTS.md

## 1. Project Overview

Asuka — 以"多人格 Agent 共存"为核心差异化的 AI 聊天应用。  
用户配置多个独立人格的 Agent，同一消息并发触发多 Agent 回应，配合 Prompt 可视化、三层记忆、插件扩展与 Live2D 虚拟形象。

---

## 2. Tech Stack

| 层次 | 技术 |
|------|------|
| 包管理 | **uv**（唯一，禁止 pip） |
| Python | 3.12+ |
| Agent 编排 | **LangGraph** `StateGraph` + `Send` 并发分支 |
| LLM 抽象 | **LangChain**（工具、链、记忆、RAG Runnable 接口）|
| API 服务 | FastAPI + uvicorn（HTTP REST + WebSocket 流式）|
| 数据库 | SQLite（本地）/ PostgreSQL（云端），SQLModel ORM |
| 向量库 | Qdrant（本地）/ `InMemoryVectorStore`（轻量）|
| 前端 | Vue 3 + TypeScript + Vite（pnpm，独立 frontend/ 目录）|
| 桌面打包 | Electron；Web 端 Vite PWA |

---

## 3. Architecture

```
Asuka/
├── asuka/                   # Python 主包
│   ├── main.py                 # FastAPI 入口 + uvicorn 启动
│   ├── config.py               # pydantic-settings 全局配置
│   │
│   ├── api/                    # 抽象层（接口/协议，不写业务逻辑）
│   │   ├── provider/           # LangChain BaseChatModel 封装，多 LLM 切换
│   │   ├── platform/           # 未来：IM 平台适配器（参考 AstrBot api/platform）
│   │   └── event/              # 事件总线接口
│   │
│   ├── core/                   # 业务实现层
│   │   ├── agent/              # Agent 配置层（静态，启动时加载）
│   │   │   ├── model.py        # Agent Pydantic schema（配置结构）
│   │   │   ├── registry.py     # 启动时从 DB 加载所有 AgentConfig，全局单例
│   │   │   ├── persona.py      # Soul / 人格 System Prompt 构建（静态）
│   │   │   └── runtime.py      # AgentRuntime：单个 Agent 在一次会话里的运行实例
│   │   │                       #   持有：compiled_graph + memory instances + agent config
│   │   │
│   │   ├── session/            # 会话运行时管理（连接配置层与执行层的桥梁）
│   │   │   ├── manager.py      # conversation_id → Session 映射（内存），生命周期管理
│   │   │   └── context.py      # 单次消息执行上下文（thread_id / agent list / input）
│   │   │
│   │   ├── graph/              # LangGraph 编排（参考 TradingAgents graph/）
│   │   │   ├── dispatch.py     # 主调度图：启动时 compile()，并发 Send → 各 Agent 分支
│   │   │   ├── nodes.py        # 无状态节点函数（build_prompt / call_llm / post_process）
│   │   │   ├── state.py        # per-turn TypedDict 状态定义
│   │   │   └── checkpointer.py # LangGraph thread_id 检查点持久化（跨轮次恢复状态）
│   │   │
│   │   ├── memory/             # 三层记忆（参考 AstrBot core/knowledge_base）
│   │   │   ├── short.py        # ConversationBufferWindowMemory
│   │   │   ├── mid.py          # ConversationSummaryMemory（LLM 自动摘要）
│   │   │   └── long.py         # VectorStoreRetriever（RAG 检索注入）
│   │   │
│   │   ├── prompt/             # Prompt 构建与可视化
│   │   │   ├── builder.py      # 7 层 Prompt 组装（Soul→Skills→Tools→Memory→User）
│   │   │   └── snapshot.py     # PromptSnapshot：各层 token 统计
│   │   │
│   │   ├── tools/              # LangChain @tool / BaseTool（参考 AstrBot core/tools）
│   │   │   └── registry.py     # 工具注册与按 Agent 分配
│   │   │
│   │   ├── plugins/            # 插件系统（参考 AstrBot builtin_stars）
│   │   │   ├── base.py         # Plugin Protocol 接口
│   │   │   ├── loader.py       # 发现、加载、版本管理
│   │   │   └── sandbox.py      # 隔离执行（restrictedpython / subprocess）
│   │   │
│   │   └── knowledge/          # 知识库 / RAG 管线
│   │       ├── loader.py       # LangChain DocumentLoader（PDF/TXT/MD/URL）
│   │       ├── indexer.py      # 分块 → Embedding → VectorStore
│   │       └── retriever.py    # 相似度检索 + 阈值过滤
│   │
│   ├── db/                     # 数据持久层
│   │   ├── models.py           # SQLModel ORM（Agent/Conversation/Message/Memory/…）
│   │   └── session.py          # 引擎 & 异步 session factory
│   │
│   └── routes/                 # FastAPI 路由（薄层，只做 HTTP → core 调用）
│       ├── agents.py           # Agent CRUD
│       ├── conversations.py    # 会话 & 消息
│       ├── knowledge.py        # 知识库管理
│       └── ws.py               # WebSocket 流式推送
│
├── plugins/                    # 官方一方插件包
├── frontend/                   # Vue 3 前端（pnpm 独立管理）
│   ├── src/
│   │   ├── components/         # 通用组件
│   │   ├── views/              # 页面（Chat / AgentConfig / PromptViz / KB）
│   │   ├── stores/             # Pinia 状态
│   │   └── live2d/             # Live2D 画布（参考 AIRI stage-ui-pixi）
│   ├── package.json
│   └── vite.config.ts
├── tests/
│   ├── conftest.py             # Fixtures（FakeListChatModel、in-memory DB）
│   ├── test_graph/
│   ├── test_memory/
│   ├── test_api/
│   └── test_plugins/
├── docs/                       # 设计文档（只读参考，不修改）
├── .env.example
└── pyproject.toml              # uv 项目配置
```

**核心调用链：**
```
WebSocket 消息
  → routes/ws.py
  → session/manager.py     查找或创建 Session（含 thread_id + AgentRuntime 列表）
  → session/context.py     构造本次调用 Context
  → graph/dispatch.py      graph.astream_events(context, config={"thread_id": ...})
      → checkpointer       自动加载上一轮状态
      → 并发 Send → nodes.py [build_prompt | call_llm | post_process]
      → checkpointer       自动保存本轮状态
  → astream_events         WebSocket 流式推送各 Agent 回复
```

---

## 4. Development Rules

- **框架优先**：LangGraph `StateGraph` 编排多 Agent；LangChain `Memory`/`Retriever`/`@tool` 直接用，不重造。
- **分层禁止**：`routes/` 只做 HTTP 映射；业务逻辑只在 `core/`；`api/` 只定义接口。
- **类型安全**：公共函数必须类型注解；数据对象用 Pydantic/SQLModel，禁用裸 `dict`。
- **最小改动**：Bug fix 不带重构；不为假设需求引入抽象。
- **命名**：文件/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_CASE`。
- **禁止**：`pip install`（统一 `uv add`）；硬编码 API Key；在 `routes/` 写业务逻辑。

---

## 5. Workflow

做功能前严格按以下顺序：

1. **读文件**：先读相关文档，确认涉及模块与当前阶段。
2. **写设计**：在 `docs/` 下对应的文件夹下补充或更新对应功能的设计文档，明确接口与数据流后再动手。(停下等用户确认)
3. **切分支**：切换到开发分支（`feat/xxx`）再写实现代码，禁止直接在 `main` 上开发。
4. **写实现**：确认 LangChain/LangGraph 框架内置方案优先复用；在 `core/` 写实现，在 `routes/` 接入。
5. **写测试**：在 `tests/` 补测试，`uv run pytest` 全绿后提交。

---

## 6. Testing & Verification

```bash
uv sync                              # 安装/更新依赖
uv run pytest                        # 全量测试
uv run pytest tests/test_graph/ -v   # 单模块
uv run ruff check asuka/          # lint
uv run mypy asuka/                # 类型检查
uv run python -m asuka.main       # 启动开发服务
```

验收标准：pytest 全绿 + ruff 无 error + mypy 无 error。  
LLM 调用在测试中用 `FakeListChatModel` mock，不发真实请求。

---

## 7. Git & Commit Rules

- 除非本轮只做分析或临时实验，否则每完成一个有意义且已验证的文件改动，都应提交一个简短、准确的 commit。
- 分支：`feat/xxx`、`fix/xxx`、`refactor/xxx`
- Commit：`type(scope): 描述`，如 `feat(graph): add concurrent dispatch via Send API`
- **不自动 push**；不提交 `.env`、`*.db`、`__pycache__/`、`*.sqlite`
- PR: 参考.github/PR_TEMPLATE/PR_TEMPLATE.md,提交pr

---

## 8. Important Constraints

- API Key 只从环境变量读取（`config.py` pydantic-settings）。
- 插件执行必须通过 `plugins/sandbox.py`，不得直接 `exec()`。
- `git push --force`、`git reset --hard`、清空向量库，需用户二次确认。
- Prompt 构建时各层有 token 软上限（见 `prompt/builder.py`），超限截断非核心层。
