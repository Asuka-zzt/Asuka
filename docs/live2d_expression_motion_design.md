# Live2D 动态表情与动作设计

依据：`docs/airi_live2d_expression_motion_research.md` 与本地参考项目 `ref/normal_agent/airi`。

## 目标

在 AsukaBot 现有 Live2D 加载能力上，补齐可由聊天事件驱动的动态表现：

- `idle`、`think`、`happy`、`sad` 四个基础情绪到 motion group 的映射与播放。
- 接入 TTS 音频，并基于真实音频驱动口型同步。
- 模型 `.exp3.json` 表情解析与参数应用。
- 后续可扩展的每帧 Live2D 参数插件链。

本轮设计优先保证与当前前端和 WebSocket 协议兼容，不要求后端立即具备完整情绪识别能力。

## 当前状态

### 前端

- `frontend/src/composables/useLive2D.ts`
  - 已加载 Cubism Core、Pixi 和 `pixi-live2d-display/cubism4`。
  - 已实现模型挂载、自适应缩放、点击身体播放 `tap_body`。
  - 暂未暴露 `playMotion()`、`setParameter()`、`setMouthOpen()` 等控制接口。
- `frontend/src/components/stage/Live2DStage.vue`
  - 只负责挂载模型和展示 loading/error/placeholder。
  - 没有监听聊天状态、情绪状态或流式 token。
- `frontend/src/stores/chat.ts`
  - 管理消息流、发送状态和连接状态。
  - 未保存 Live2D 指令或情绪。
- `frontend/src/types/chat.ts`
  - WebSocket 事件仅支持 `token`、`done`、`error`。
- TTS
  - 当前代码中尚未发现已实现的 TTS provider 或 `/api/tts` 路由。
  - `docs/语言教学设计.md` 已规划 `edge-tts`：`api/provider/tts.py` 封装合成，`routes/tts.py` 提供 `POST /api/tts` 返回 `audio/mpeg`。

### 模型资源

内置 `frontend/public/live2d/Frieren/Frieren.model3.json`：

- `Expressions` 已列出多组 `.exp3.json`。
- `Motions` 只有空字符串 group，包含 `daiji.motion3.json`、`zs1.motion3.json`。
- 没有 `Idle`、`Happy`、`Sad`、`Think` 等 AIRI 默认 motion group。

因此情绪映射必须可配置并具备降级策略，不能硬编码 AIRI 的 group 名称。

## AIRI 可复用点

AIRI 的实现可以作为结构参考，但不直接整体迁移：

- `constants/emotions.ts`：情绪枚举与 emotion -> motion group 映射。
- `expression-controller.ts`：读取 `model3.json` 的 `Expressions`，fetch `.exp3.json`，按 `Add`、`Multiply`、`Overwrite` blend 写入参数。
- `motion-manager.ts`：hook `motionManager.update`，把 expression、blink、idle eye、lipsync 放入每帧插件链。

AsukaBot 当前代码量较小，建议先实现简化版控制层，再逐步演进到插件链。

## 数据流

### 兼容现状的数据流

```text
WS token
  -> useChatSocket.appendToken()
  -> chat store streaming/sending 状态变化
  -> Live2DStage 监听 sending/streaming
  -> useLive2D.playMotion('think' 对应 motion group 或 fallback)

assistant final text
  -> POST /api/tts
  -> audio/mpeg
  -> frontend audio element / Web Audio analyser
  -> mouthOpen
  -> useLive2D.setMouthOpen(audio-derived value)
```

### 预留结构化 Live2D 指令

后端后续可以新增事件：

```ts
type WsEvent =
  | { type: 'token'; content: string }
  | { type: 'done' }
  | { type: 'error'; content: string }
  | {
      type: 'live2d.emotion'
      emotion: EmotionType
      motion?: string
      expression?: string
      durationMs?: number
      intensity?: number
    }
```

前端收到 `live2d.emotion` 后写入 Live2D store。`motion` 优先级高于 `emotion` 映射，便于模型定制。

## 类型设计

新增 `frontend/src/types/live2d.ts`：

```ts
export type EmotionType =
  | 'idle'
  | 'happy'
  | 'sad'
  | 'think'

export interface Live2DMotionCommand {
  group: string
  index?: number
  fallbackGroups?: string[]
}

export interface Live2DExpressionCommand {
  name: string
  durationMs?: number
  intensity?: number
}

export interface Live2DInstruction {
  emotion?: EmotionType
  motion?: Live2DMotionCommand
  expression?: Live2DExpressionCommand
}
```

新增 `frontend/src/stores/live2d.ts`：

- 保存当前 `emotion`、`motionCommand`、`expressionCommand`、`speaking`、`mouthOpen`。
- 提供 `setEmotion()`、`setThinking()`、`setSpeaking()`、`clearInstruction()`。
- 先用内存状态，不做持久化。

新增后端 TTS：

- `asukabot/api/provider/tts.py`：封装 `edge-tts` 合成。
- `asukabot/routes/tts.py`：`POST /api/tts`，输入文本和可选 voice，返回 `audio/mpeg`。
- `asukabot/config.py`：TTS voice/rate 配置从环境变量读取。

## Motion 策略

阶段 1 只强制四个基础情绪映射：

| emotion | 默认 group | 触发时机 |
|---|---|
| idle | `Idle` | 无发送、无播放、TTS 结束 |
| think | `Think` | 用户消息已发送，等待模型回复或 TTS 准备中 |
| happy | `Happy` | 后端或前端解析到高兴情绪 |
| sad | `Sad` | 后端或前端解析到悲伤情绪 |

AsukaBot 增加环境变量覆盖：

- `VITE_LIVE2D_MOTION_IDLE`
- `VITE_LIVE2D_MOTION_THINK`
- `VITE_LIVE2D_MOTION_HAPPY`
- `VITE_LIVE2D_MOTION_SAD`

降级规则：

1. 若事件显式带 `motion.group`，先播放该 group。
2. 否则按环境变量映射查找。
3. 若未配置，使用表格中的默认 group。
4. 若播放失败或模型没有该 group，不中断 UI，仅记录 warning。
5. 对 Frieren 这类只有空 group 的模型，允许 `VITE_LIVE2D_MOTION_THINK=` 或 `VITE_LIVE2D_MOTION_IDLE=` 映射到空 group；代码不能把空字符串当作无效值。

## 口型策略

阶段 1 必须接入 TTS 音频，不做文本估算口型。原因：没有语音时模型嘴动会显得割裂，Live2D 的口型应与实际播放的声音同步。

推荐采用 `edge-tts` 作为首个 TTS provider：

- 与 `docs/语言教学设计.md` 中的 TTS 规划一致。
- 免费、无需 API Key，适合 MVP。
- 后端负责生成 MP3，前端只播放和分析音频，不暴露外部 TTS 服务细节。

口型数据流：

```text
assistant final text
  -> POST /api/tts { text, voice? }
  -> audio/mpeg
  -> HTMLAudioElement.play()
  -> AudioContext + AnalyserNode
  -> mouthOpen RMS / volume envelope
  -> Live2D final plugin
  -> ParamMouthOpenY
```

实现约束：

- TTS 播放开始后再进入 `speaking` 状态。
- 仅在有音频播放时写入非零 `ParamMouthOpenY`。
- TTS 播放结束或失败时，200ms 内平滑回到 0，并切回 `idle`。
- 音频失败时可以继续显示文字回复，但不启动口型。
- 后续如需要更精确口型，再接 AIRI 使用的 `wlipsync` 或同类 worklet；MVP 先用 Web Audio 分析音量包络。

## Expression 策略

阶段 2 实现 `.exp3.json` 表情：

1. 模型加载后读取 `model.internalModel.settings.expressions` 或等价设置对象。
2. 根据 model URL 解析模型根目录，fetch 每个 `.exp3.json`。
3. 解析参数：
   - `Id`
   - `Value`
   - `Blend`: `Add`、`Multiply`、`Overwrite`
4. 保存 expression group 到 Live2D store。
5. 每帧在 SDK motion update 后写入参数。

Blend 规则：

- `Add`: `modelDefault + value * intensity`
- `Multiply`: `currentFrameValue * value`
- `Overwrite`: `lerp(modelDefault, value, intensity)`

风险：

- SDK 内置 expression manager 可能覆盖同一参数。实现时需要确认 `pixi-live2d-display` 暴露的 expression manager 行为，再决定禁用或在 final 阶段覆盖。
- 参数默认值需要从 `coreModel.getParameterValueById()` 初始化，不能硬编码 0。

## 每帧插件链

阶段 3 将口型和表情统一到简化插件链：

```ts
export interface Live2DFrameContext {
  coreModel: {
    getParameterValueById: (id: string) => number
    setParameterValueById: (id: string, value: number) => void
  }
  now: number
  deltaMs: number
}

export type Live2DFramePlugin = (ctx: Live2DFrameContext) => void
```

执行顺序：

1. SDK 原始 motion update。
2. expression plugin。
3. lipsync plugin。
4. idle eye / blink fallback plugin。

先不强行接管所有 motionManager 行为；只有当 expression 和口型互相覆盖时，再 hook `motionManager.update`。

## 实施阶段

### 阶段 1：控制接口 + 四基础情绪 motion + TTS 口型

改动范围：

- `asukabot/api/provider/tts.py`
- `asukabot/routes/tts.py`
- `asukabot/config.py`
- `asukabot/main.py`
- `pyproject.toml`
- `frontend/src/types/live2d.ts`
- `frontend/src/stores/live2d.ts`
- `frontend/src/api/client.ts`
- `frontend/src/composables/useLive2D.ts`
- `frontend/src/composables/useTtsAudio.ts`
- `frontend/src/components/stage/Live2DStage.vue`
- `frontend/src/types/chat.ts`
- `frontend/src/composables/useChatSocket.ts`

验收：

- 配置 `VITE_LIVE2D_MODEL_URL=/live2d/Frieren/Frieren.model3.json` 后模型正常加载。
- 点击模型不报错。
- 发送消息时进入 `think` motion。
- 至少支持 `idle`、`think`、`happy`、`sad` 四个情绪映射。
- 回复完成后调用 `/api/tts` 生成音频并播放。
- 只有音频播放时 `ParamMouthOpenY` 随音量变化。
- 收到 `done/error` 后 mouthOpen 回落。
- TTS 失败时不触发口型，文字聊天仍可用。
- `uv run pytest tests/test_routes/ -v` 通过。
- `uv run ruff check asukabot/` 通过。
- `uv run mypy asukabot/` 通过。
- `pnpm --dir frontend lint` 通过。

### 阶段 2：Expression controller

改动范围：

- `frontend/src/live2d/expression-controller.ts`
- `frontend/src/stores/live2d.ts`
- `frontend/src/composables/useLive2D.ts`

验收：

- 能列出 Frieren 的 expression names。
- 调用 `setExpression('ku')` 后对应参数被写入。
- duration 到期后参数回到默认值。

### 阶段 3：结构化 WS 指令

改动范围：

- `asukabot/routes/ws.py`
- `frontend/src/types/chat.ts`
- `frontend/src/composables/useChatSocket.ts`
- 后续 Agent prompt 或 post-process 情绪解析模块。

验收：

- 后端可推送 `live2d.emotion`。
- 前端收到后按 emotion/motion/expression 驱动模型。
- 旧客户端仍能处理 `token/done/error`。

## 测试计划

- 前端：
  - `pnpm --dir frontend lint`
  - 手动在浏览器验证 Live2D 挂载、消息发送、TTS 播放、音频驱动口型变化。
- 后端：
  - `uv run pytest tests/test_routes/ -v`
  - `uv run ruff check asukabot/`
  - `uv run mypy asukabot/`

## 暂不实现

- 不直接迁移 AIRI 完整 settings UI。
- 阶段 1 不引入 `wlipsync`，先用 Web Audio 音量包络驱动口型。
- 不做自然语言到骨骼动作生成。
- 不修改原有设计文档，只以本文作为本次 Live2D 功能的追加设计。

## 阶段 1.1：切块流式 TTS

问题：阶段 1 在收到完整 `done` 后才调用 `/api/tts`，用户会先看到完整回复，再等待 TTS 合成和下载，语音响应明显滞后。

目标：前端看到回复文本时尽快听到声音，不等待整段回复完成。

约束：

- 不做逐 token TTS。单字或短 token 会导致请求过多、声音断裂、语调不自然。
- 前端按句子边界或最小长度切块，例如 `。！？!?；;` 或累计到约 48 字。
- 每个切块进入 TTS 队列，按顺序播放，保证语音顺序与文字顺序一致。
- 后端新增 `/api/tts/stream`，使用 `StreamingResponse` 透传 `edge-tts` 的 audio chunk。
- 前端默认按切块完整 Blob 顺序播放，避免 MP3 MediaSource 在部分浏览器中只播放首个 frame 后卡住。
- `/api/tts/stream` 保留为后续优化入口；只有确认浏览器与音频格式兼容后再启用 MediaSource 边下载边播放。
- Live2D 口型仍只由真实音频播放驱动，不因 token 到达而假动。

数据流：

```text
WS token
  -> append assistant text
  -> TTS chunker accumulates token text
  -> sentence boundary / min length reached
  -> enqueue chunk
  -> GET/POST /api/tts/stream
  -> MediaSource append audio/mpeg chunks
  -> audio starts before full assistant message is done
  -> Web Audio analyser drives ParamMouthOpenY
```

验收：

- 首个句子或首个足够长片段出现后即可开始合成和播放。
- 后续片段排队顺序播放，不互相覆盖。
- `done` 时 flush 剩余文本。
- 新消息发送时停止当前播放并清空旧队列。
- TTS 失败只跳过当前片段，不影响文字流。

补充修复：

- TTS 入队不再直接依赖单个 token，而是基于完整 assistant 文本快照计算增量，降低中间 token/文本块漏入队风险。
- 入队前统一清洗朗读文本：去除 Markdown 控制符、链接 URL、代码围栏、emoji、`[emotion:*]` 等控制标签。
- `*`、emoji、Markdown 装饰被读出来是输入清洗问题，不优先通过更换 TTS 模型解决；只有清洗后语调或稳定性仍不满足，再评估其他 TTS provider。
