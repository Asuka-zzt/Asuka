# AIRI Live2D 动态表情与肢体语言调研

调研对象：`ref/normal_agent/airi`

调研问题：AIRI 是否已经实现 Live2D 模型的动态表情、动态肢体语言，以及这些能力对 Asuka 的可复用价值。

## 结论

AIRI 已经实现了较完整的 Live2D 舞台能力，不是占位实现。

- 动态表情：已实现。AIRI 能解析 `model3.json` 中的 `Expressions` 配置，读取 `.exp3.json`，将表达式参数注册到 Pinia store，并在每帧覆盖到 Cubism 参数上。
- 情绪驱动动作：已实现。聊天流中的 `act.emotion` 会映射为 Live2D motion group，例如 `happy -> Happy`、`think -> Think`、`neutral -> Idle`。
- 动态肢体语言：部分实现。AIRI 支持播放模型内置 motion group、点击身体触发 `tap_body`、发送前进入 `Think` motion、可设置运行时 idle motion 循环。但它不是基于自然语言自动生成骨骼动作，而是“LLM/事件 -> motion group/参数”的控制方式。
- 口型同步：已实现。AIRI 使用 `wlipsync` 从音频中计算 mouth open，再在 Live2D 每帧写入 `ParamMouthOpenY`。
- 眼动/眨眼：已实现。支持鼠标/窗口坐标眼动、idle 眼神漂移、SDK/自研强制自动眨眼。
- LLM 直接控制表情工具：有工具定义，但未发现被接入全局工具链。`expression_set/get/toggle/reset` 存在于源码中，但 `rg` 只搜到定义，没有搜到调用或注册点。

因此，对 Asuka 来说，AIRI 的 Live2D 部分可以作为前端实现参考，尤其是 `stage-ui-live2d` 的包拆分、motion manager 插件链、表达式 store、口型同步和情绪到 motion 的数据流。

## 关键源码路径

| 模块 | 路径 | 作用 |
|---|---|---|
| Live2D 场景入口 | `ref/normal_agent/airi/packages/stage-ui-live2d/src/components/scenes/Live2D.vue` | 组合 Canvas、Model、配置项、鼠标眼动 |
| Live2D 模型运行时 | `ref/normal_agent/airi/packages/stage-ui-live2d/src/components/scenes/live2d/Model.vue` | 加载模型、挂载 Pixi stage、注册 motion/update 插件 |
| 表情控制器 | `ref/normal_agent/airi/packages/stage-ui-live2d/src/composables/live2d/expression-controller.ts` | 解析 `.exp3.json` 并每帧应用表达式参数 |
| 表情状态 store | `ref/normal_agent/airi/packages/stage-ui-live2d/src/stores/expression-store.ts` | 保存表达式、默认值、toggle、auto-reset |
| motion manager | `ref/normal_agent/airi/packages/stage-ui-live2d/src/composables/live2d/motion-manager.ts` | 插件化接管 motion update、眨眼、眼动、表情、口型 |
| 情绪映射 | `ref/normal_agent/airi/packages/stage-ui-live2d/src/constants/emotions.ts` | 定义 emotion 到 Live2D motion group 的映射 |
| 舞台集成 | `ref/normal_agent/airi/packages/stage-ui/src/components/scenes/Stage.vue` | 连接聊天流、TTS、口型、Live2D/VRM/Spine |
| 口型驱动 | `ref/normal_agent/airi/packages/model-driver-lipsync/src/live2d/index.ts` | 基于 `wlipsync` 输出 `mouthOpen` |
| 表情工具 | `ref/normal_agent/airi/packages/stage-ui-live2d/src/tools/expression-tools.ts` | 定义 LLM 可调用的 expression tools |

## 实现细节

### 1. Live2D 模型加载与舞台挂载

`Model.vue` 使用 `pixi-live2d-display/cubism4` 的 `Live2DFactory.setupLive2DModel()` 加载模型，并把模型加入 Pixi stage。

关键点：

- 使用 `Live2DModel<PixiLive2DInternalModel>()` 创建模型实例。
- `autoInteract: false`，说明 AIRI 自己接管交互和 motion 管理。
- 加载后读取 `internalModel.motionManager`、`coreModel`。
- 点击命中 `body` 时触发 `model.motion('tap_body')`。

对应代码位置：

- `Model.vue:253-268`：创建并加载模型，加入 stage。
- `Model.vue:276-279`：点击身体触发 `tap_body`。
- `Model.vue:283-286`：取得 Cubism core model 和 motion manager。

### 2. 情绪到 Live2D motion

AIRI 的情绪类型包括：

`happy`、`sad`、`angry`、`think`、`surprised`、`awkward`、`question`、`curious`、`neutral`。

Live2D 映射为：

| emotion | motion group |
|---|---|
| happy | `Happy` |
| sad | `Sad` |
| angry | `Angry` |
| think | `Think` |
| surprised | `Surprise` |
| awkward | `Awkward` |
| question | `Question` |
| curious | `Curious` |
| neutral | `Idle` |

对应代码：

- `constants/emotions.ts:1-35` 定义情绪和 motion group 映射。
- `Stage.vue:139-158` 创建情绪队列；当 renderer 是 `live2d` 时，把 emotion 映射为 `currentMotion`。
- `Stage.vue:187-202` 处理流式控制信号 `act`，支持 `act.motion` 直接指定 Live2D motion，也支持 `act.emotion` 转换后入队。
- `Stage.vue:672-674` 在发送消息前把当前 motion 置为 `Think`。
- `Model.vue:488-502` 通过 `model.value.motion(motionName, index, MotionPriority.FORCE)` 播放 motion。
- `Model.vue:551` watch `currentMotion` 并执行 `setMotion()`。

判断：AIRI 已经实现“聊天事件驱动动作”，但动作质量依赖模型是否内置相同名称的 motion group。

### 3. 表情系统

表情系统是 AIRI 当前 Live2D 实现里最值得借鉴的部分。

`expression-controller.ts` 负责：

- 读取 `model3.json` 的 `settings.expressions`。
- 逐个 fetch 对应 `.exp3.json`。
- 解析每个参数的 `Id`、`Value`、`Blend`。
- 注册 expression group 和 parameter entry。
- 每帧根据 blend mode 写入 Cubism 参数。

对应代码：

- `expression-controller.ts:74-133`：初始化并注册 exp3 表情。
- `expression-controller.ts:154-180`：每帧应用 active expression。
- `expression-controller.ts:188-219`：支持 `Add`、`Multiply`、`Overwrite` 三种 blend。
- `Model.vue:461-486`：从模型 settings 初始化 expression controller。
- `Model.vue:420-436`：开启 expression 时禁用 SDK 内置 expression manager 和 eyeBlink，避免覆盖 AIRI 的最终参数。

状态管理：

- `expression-store.ts:107-190` 保存 modelId、expressionGroups、expression parameter entries。
- `expression-store.ts:211-239` 支持 `set(name, value, duration)`。
- `expression-store.ts:279-315` 支持 `toggle(name, duration)`。
- `expression-store.ts:321-347` 支持保存默认值和重置。

注意：

- `useSettingsLive2d()` 中 `live2dExpressionEnabled` 默认值是 `false`，见 `live2d.ts:30`。
- `Model.vue` 的 prop 默认值是 `true`，但在真实场景中 `Live2D.vue` 会把 settings store 的值传入，因此实际舞台默认是否启用取决于本地设置。

### 4. Motion update 插件链

AIRI 没有直接依赖 SDK 的默认 update 行为，而是 hook 了 `motionManager.update`，加入插件链。

执行顺序：

1. pre plugins
2. SDK 原始 `motionManager.update`
3. post plugins
4. final plugins

对应代码：

- `motion-manager.ts:56-142` 定义 update hook 和插件注册。
- `Model.vue:340-367` 创建 motion manager update 并替换原始 `motionManager.update`。

已注册插件：

- `useMotionUpdatePluginBeatSync()`：基于节拍驱动 `ParamAngleX/Y/Z`。
- `useMotionUpdatePluginIdleDisable()`：禁用 idle motion 时停止 motion，并可保留眼动/眨眼。
- `useMotionUpdatePluginIdleFocus()`：idle 时眼神漂移。
- `useMotionUpdatePluginExpression()`：每帧应用 expression 参数。
- `useMotionUpdatePluginAutoEyeBlink()`：自动眨眼。
- `useMotionUpdatePluginLipSync()`：口型同步。

对应代码：

- `Model.vue:353-362` 注册这些插件。
- `motion-manager.ts:146-209` beat sync。
- `motion-manager.ts:212-247` idle 禁用与 idle 眼动。
- `motion-manager.ts:249-440` 自动眨眼。
- `motion-manager.ts:450-457` 表情 final plugin。
- `motion-manager.ts:466-499` 口型 final plugin。

判断：AIRI 的动态肢体语言不是单点函数，而是每帧参数管线。这个结构适合 Asuka 复用。

### 5. 口型同步

AIRI 的口型同步链路：

1. `Stage.vue` 在消息开始前调用 `setupLipSync()`。
2. `createLive2DLipSync()` 创建 `wlipsync` worklet。
3. TTS 播放时 `nowSpeaking = true`。
4. `requestAnimationFrame` 循环读取 `live2dLipSync.getMouthOpen()`。
5. `mouthOpenSize` 传给 `Live2DScene`。
6. `Model.vue` 的 motion final plugin 写入 `ParamMouthOpenY`。

对应代码：

- `Stage.vue:481-496` lip sync rAF 循环。
- `Stage.vue:531-551` 创建 Live2D lip sync。
- `Stage.vue:876-893` 把 `mouthOpenSize`、`nowSpeaking` 传给 `Live2DScene`。
- `motion-manager.ts:466-499` 将 `mouthOpenSize` 写入 `ParamMouthOpenY`，并在说话结束后做 200ms 平滑释放。
- `model-driver-lipsync/src/live2d/index.ts:71-157` 基于 `wlipsync` 输出 mouth open。

判断：AIRI 已经实现音频驱动口型，不只是文本估算。

### 6. 眼动与自动眨眼

AIRI 支持两种眼动来源：

- 鼠标/窗口坐标输入：`Live2D.vue` 接收 `cursorPosition`，`eye-tracking.ts` 转换成 `Live2DModel.focus(x, y)` 所需坐标。
- idle 眼动：当无外部 focus source 时，`useLive2DIdleEyeFocus()` 做眼神漂移。

对应代码：

- `Live2D.vue:43-62` 读取 Live2D settings，生成 `mouseFocus`。
- `Live2D.vue:64-71` cursor 位置 1 秒后失效，回到 idle。
- `Live2D.vue:106-128` 把 eye tracking、idle eye、blink 配置传入 model。
- `eye-tracking.ts:28-59` 坐标换算。
- `motion-manager.ts:236-247` idle focus plugin。
- `motion-manager.ts:249-440` 自动眨眼 plugin。

判断：AIRI 已经实现“模型看向用户/鼠标”和“无输入时自然眼动”的动态表现。

### 7. LLM 表情工具现状

`expression-tools.ts` 定义了 5 个工具：

- `expression_set`
- `expression_get`
- `expression_toggle`
- `expression_save_defaults`
- `expression_reset_all`

这些工具可以让 LLM 或工具调用层直接操作 Live2D 表情或参数，支持 duration 自动复位。

但当前本地源码中：

```bash
rg -n "expressionTools|expression-tools|expression_set|expression_get|expression_toggle|expression_save_defaults|expression_reset_all" ref/normal_agent/airi
```

只搜索到 `expression-tools.ts` 自身定义，未发现接入全局工具注册或聊天工具链。因此判断为：工具接口已经设计和实现，但未确认已在产品主流程启用。

## 与 Asuka 当前实现差距

Asuka 当前前端已有 Live2D 加载和基础交互：

- `frontend/src/composables/useLive2D.ts` 能加载 Cubism Core、Pixi、`pixi-live2d-display/cubism4`。
- 当前有 `model.motion?.('tap_body')`。

但与 AIRI 相比，Asuka 还缺：

1. 情绪类型与 motion group 映射。
2. 从聊天流解析 `emotion/act` 并驱动 Live2D 的前端状态机。
3. expression controller：读取 `.exp3.json`、注册表达式、每帧应用参数。
4. motion update 插件链。
5. 口型同步。
6. 鼠标/idle 眼动与自动眨眼兜底。
7. 表情/动作配置 UI。
8. 模型导入与结构校验。

## 对 Asuka 的建议实现顺序

### 阶段 1：补齐情绪到 motion

目标：用最小改动让 Agent 回复驱动动作。

- 定义 `EmotionType`：`happy/sad/angry/think/surprised/awkward/question/curious/neutral`。
- 前端建立 `emotion -> motionGroup` 映射。
- WebSocket 支持 `live2d.emotion` 或在消息 payload 中带 `emotion`。
- `useLive2D` 暴露 `playMotion(group, index?)`。
- `Live2DStage` 监听 emotion 后调用 `playMotion()`。

这一步不需要实现 exp3 表情系统，风险最低。

### 阶段 2：接入基础口型

目标：说话时嘴动。

- 如果当前没有真实 TTS 音频，先用文本流估算 `ParamMouthOpenY`。
- 有 TTS 后再参考 AIRI 的 `wlipsync` 方式做音频驱动。
- `useLive2D` 暴露 `setParameter('ParamMouthOpenY', value)` 或内部专用 `setMouthOpen(value)`。

### 阶段 3：实现 expression controller

目标：支持模型自带 `.exp3.json` 表情。

- 读取 `model.internalModel.settings.expressions`。
- fetch 每个 exp3 文件。
- 存入前端 expression store。
- 每帧在 ticker 或 motion update 后写入参数。
- 注意禁用或协调 SDK 内置 expression manager，避免互相覆盖。

### 阶段 4：插件化 motion update

目标：让表情、眨眼、口型、眼动可组合。

AIRI 的 motion manager 插件链值得直接借鉴。Asuka 可以先实现简化版：

```ts
type Live2DFramePlugin = (ctx: {
  coreModel: CubismCoreModel
  now: number
  delta: number
}) => void
```

然后依次加入：

- expression plugin
- blink plugin
- lipsync plugin
- idle eye plugin

## 风险与注意点

- 模型资源差异大：motion group 名称不统一，`Happy`/`Sad` 等映射需要可配置。
- `.exp3.json` 的参数范围和 blend 方式需要按模型读取，不能硬编码。
- SDK 内置 expression manager、eyeBlink、motion curves 会互相覆盖，需要明确每帧写入顺序。
- Live2D 的“肢体语言”本质依赖模型预制 motion 或参数 rig，不能单靠代码生成高质量动作。
- Asuka 当前架构应优先把 Live2D 控制保持在前端，后端只下发结构化情绪/动作指令。

## 结论给产品

AIRI 的这部分功能已经实现到可参考、可迁移的程度：

- 表情：实现较完整，支持 exp3、参数 blend、持久默认值、auto reset。
- 动作：实现可用，支持 emotion/act -> motion group，但依赖模型内置动作。
- 口型：实现完整，基于 TTS 音频。
- 眼动/眨眼：实现完整。
- LLM 表情工具：有定义，但本地源码未发现主流程接入。

Asuka 如果要追 AIRI 的体验，建议先做“情绪到 motion + 口型 + 基础参数控制”，再做 exp3 表情系统和插件化 update 管线。
