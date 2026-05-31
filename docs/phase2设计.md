# Phase 2 设计 — 最小可对话 Agent

> 目标：WebSocket 连接后能与单个 Agent 多轮对话，上下文不丢失。默认模型 DeepSeek，真实 LLM 手动验收。

## 1. 范围

**做：** 单 Agent、WebSocket 流式对话、多轮记忆（checkpointer）、DeepSeek provider。
**不做：** 多 Agent 并发、工具调用（Phase 3）、前端、session/manager（用 conversation_id 直接当 thread_id）。

---

## 2. 新增文件与职责

```
asukabot/
├── api/provider/__init__.py     get_llm(model_id) → BaseChatModel
├── core/agent/model.py          AgentConfig（Pydantic）
├── core/graph/dispatch.py       build_agent() → create_react_agent
├── core/graph/checkpointer.py   get_checkpointer() → AsyncSqliteSaver
└── routes/
    ├── __init__.py
    ├── chat.py                  POST /chat（非流式，调试）
    └── ws.py                    WS /ws/{conversation_id}（流式）
```

---

## 3. 接口设计

### 3.1 Provider 层 `api/provider/__init__.py`

```python
def get_llm(model_id: str) -> BaseChatModel:
    """按 model_id 前缀路由到对应 provider 适配器。"""
```

路由规则（MVP）：

| model_id 前缀 | 适配器 | 说明 |
|---|---|---|
| `deepseek-*` | `ChatOpenAI(base_url="https://api.deepseek.com")` | DeepSeek OpenAI 兼容接口，默认 |
| `gpt-*` | `ChatOpenAI` | OpenAI |
| `claude-*` | `ChatAnthropic` | Anthropic |

DeepSeek 复用 `langchain-openai` 的 `ChatOpenAI`，仅改 `base_url` + `api_key`，**不引入额外依赖**。

### 3.2 Agent 配置 `core/agent/model.py`

```python
class AgentConfig(BaseModel):
    id: str = "default"
    name: str = "Asuka"
    soul: str = "你是 Asuka，一个友好、简洁的 AI 助手。"   # System Prompt
    model_id: str = "deepseek-chat"
```

Phase 2 用一个硬编码的 default agent，不接 DB（DB 在后续阶段）。

### 3.3 图构建 `core/graph/dispatch.py`

```python
async def build_agent(config: AgentConfig):
    return create_react_agent(
        model=get_llm(config.model_id),
        tools=[],                      # Phase 3 注入 wiki_generator
        prompt=config.soul,
        checkpointer=await get_checkpointer(),
    )
```

用 LangGraph 预构建 `create_react_agent`，不手写 StateGraph。

### 3.4 Checkpointer `core/graph/checkpointer.py`

```python
async def get_checkpointer() -> AsyncSqliteSaver:
    """全局单例，落盘 settings.session_db。"""
```

多轮记忆完全交给 `AsyncSqliteSaver`，`thread_id = conversation_id`。

---

## 4. 路由与配置

### 4.1 配置新增（`config.py`）

```
deepseek_api_key: str = ""
deepseek_base_url: str = "https://api.deepseek.com"
default_model: str = "deepseek-chat"   # 改默认
```

### 4.2 WebSocket `routes/ws.py`

```
WS /ws/{conversation_id}
  ← 客户端发送：{"message": "..."}
  → graph.astream_events(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": conversation_id}},
    )
  → 流式推送：{"type": "token", "content": "..."}   # 增量
  → 结束推送：{"type": "done"}
```

只监听 `on_chat_model_stream` 事件，提取 token 增量推送。

### 4.3 调试接口 `routes/chat.py`

```
POST /chat  body={"conversation_id": "...", "message": "..."}
  → graph.ainvoke(...)
  → {"reply": "完整回复"}
```

### 4.4 `main.py` 挂载路由

```python
app.include_router(chat.router)
app.include_router(ws.router)
```

---

## 5. 数据流

```
WS /ws/conv-123  ← {"message": "你好"}
  → build_agent(default_config)（首次构建，之后复用）
  → astream_events(input, thread_id="conv-123")
      → checkpointer 加载 conv-123 历史
      → DeepSeek 流式生成
      → on_chat_model_stream → 推送 token
      → checkpointer 保存本轮
  → {"type": "done"}

第二条消息 conv-123 ← {"message": "我刚才说了什么？"}
  → checkpointer 自动带出上一轮上下文 → Agent 能正确回答
```

---

## 6. 验收（真实 LLM 手动测试）

前置：`.env` 配置 `DEEPSEEK_API_KEY`。

```bash
uv run python -m asukabot.main      # 启动
# 用 wscat / Python 客户端连 ws://127.0.0.1:8000/ws/test-conv
> {"message": "你好，记住我的幸运数字是 7"}
< 流式 token... done
> {"message": "我的幸运数字是多少？"}
< "...7"    ← 验证多轮记忆生效
```

**验收标准：**
- ✓ WebSocket 流式返回 token，能看到逐字输出
- ✓ 第二轮能记得第一轮内容（checkpointer 生效）
- ✓ `POST /chat` 非流式返回完整回复
- ✓ ruff / mypy 全绿

---

## 7. 风险

| 风险 | 对策 |
|---|---|
| DeepSeek base_url / 模型名变动 | 集中在 provider 层，单点修改 |
| checkpointer 异步连接生命周期 | 用 `AsyncSqliteSaver` + 应用级单例，lifespan 管理 |
| astream_events 事件结构版本差异 | 锁定 langgraph 版本；只依赖 `on_chat_model_stream` |
