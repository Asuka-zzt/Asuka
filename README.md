# Asuka

**多人格 Agent 共存的 AI 聊天应用**。

用户配置多个独立人格的 Agent，同一消息并发触发多 Agent 回应，配合 Prompt 可视化、三层记忆、插件扩展与 Live2D 虚拟形象。

---

## 快速开始

### 环境准备

- Python >= 3.12 + [uv](https://docs.astral.sh/uv/)（**唯一** Python 包管理器，禁止使用 pip）
- Node.js + pnpm（推荐执行 `corepack enable pnpm`）

### 后端启动

```bash
# 1. 安装依赖
uv sync

# 2. 准备配置（至少需要一个 LLM Provider 的 API Key）
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（或其他 OPENAI_API_KEY / ANTHROPIC_API_KEY）

# 3. 启动开发服务器（默认监听 127.0.0.1:8000，支持热重载）
uv run python -m asuka.main
```

启动成功后可验证：

```bash
curl http://127.0.0.1:8000/health
# {"status": "ok", "version": "0.1.0"}
```

### 前端启动

**新开一个终端**：

```bash
# 首次安装前端依赖
pnpm --dir frontend install

# 启动 Vite 开发服务器（默认 5173 端口）
pnpm --dir frontend dev
```

浏览器访问：**http://localhost:5173**

- 主界面：左 Live2D 舞台 + 右聊天面板（WebSocket 流式对话）
- 学习页：`/learn`（英语/日语老师、纠错卡片、测验卡片、TTS 朗读）
- 其他视图：`/agent`（Agent 测试台，非流式）、`/wiki`（代码库生成 Wiki）

> 前端开发服务器通过 Vite proxy 自动转发 `/ws`、`/chat`、`/health` 等请求到后端，无需处理 CORS。

### 同时运行提示

- 后端与前端分别用两个终端运行。
- 后端必须先于前端启动（或至少在前端访问时已就绪）。
- 健康徽标会自动轮询后端状态。

---

## 常用开发命令

### 后端（项目根目录）

```bash
uv run pytest                  # 全量测试
uv run pytest tests/test_graph/ -v
uv run ruff check asuka/       # lint
uv run mypy asuka/             # 类型检查
uv run python -m asuka.main    # 启动开发服务
```

### 前端（项目根目录或 frontend/ 目录）

```bash
pnpm --dir frontend dev        # 开发
pnpm --dir frontend build      # 生产构建
pnpm --dir frontend preview    # 预览构建结果
pnpm --dir frontend lint       # 类型检查（vue-tsc）
```

---

## 配置说明

所有敏感信息仅通过环境变量读取（使用 pydantic-settings）。

- 复制 `.env.example` 为 `.env` 并填写 Key。
- 默认后端端口 8000，可通过 `HOST` / `PORT` / `DEBUG` 调整。
- 前端独立部署时可设置 `VITE_API_BASE` 和 `VITE_WS_BASE`（详见 `docs/开发启动指南.md`）。

数据目录 `./data`（会话 DB）和输出目录 `./output` 会在首次使用时自动创建。

---

## 更多文档

- 开发规范与工作流：`AGENTS.md`
- 架构与设计：`docs/概要设计.md`、`docs/前端设计.md` 等（`docs/` 目录下的设计文档均以追加方式添加，不直接修改原有文档）
- 完整开发启动细节与排查：参考 `docs/开发启动指南.md`
- 语言教学设计：参考 `docs/edu/语言教学设计.md`

---

## 技术栈

- 后端：FastAPI + uvicorn + LangGraph + LangChain + SQLite
- 前端：Vue 3 + TypeScript + Vite + UnoCSS + Pinia + pixi-live2d-display
- 包管理：uv（Python） / pnpm（前端）

当前活跃分支包含 Live2D 虚拟形象、TTS 集成与语言教学功能。

---

**贡献前请阅读 `AGENTS.md` 中的完整工作流（读文件 → 写设计 → 切分支 → 实现 → 测试）。**
