# Live2D 阶段4 设计 — 插件化 motion update（每帧参数管线）

> 落地 `live2d_expression_motion_design.md` 的「每帧插件链」一节，对应
> `airi_live2d_expression_motion_research.md` 路线图 **阶段4：插件化 motion update**。
> 沿用该节定义的 `Live2DFrameContext`（字段 `coreModel`）/ `Live2DFramePlugin` 接口。
> 目标：把 expression / 自动眨眼 / 口型 / idle 眼动 组织成**每帧参数管线**（`Live2DFramePlugin`），
> 并补齐研究文档列出的差距 5/6（口型按帧写、鼠标/idle 眼动与自动眨眼兜底）。
> 复用现有 `useLive2D` + Pinia store + Stage 的数据流，**不另起炉灶、最小改动**。
>
> 本文为设计阶段产出，按 AGENTS.md §5 工作流：写设计 → **停下等用户确认** → 切实现 → 测试。

---

## 1. 现状与问题（诚实标注）

| 现状 | 文件 | 问题 |
|---|---|---|
| 模型 `autoInteract: true`，SDK 自带每帧 update（motion + `expressionManager` + 内置 `eyeBlink` + physics + focus） | `useLive2D.ts:175` | SDK 自带眨眼/物理已在跑，但无法被我们协调 |
| 口型用响应式 watch 写参数：store `mouthOpen` 变化 → `setMouthOpen` 立刻写 `ParamMouthOpenY` | `Live2DStage.vue:58`、`useLive2D.ts:259` | **写在帧循环之外**，可能被 SDK 当帧 update 覆盖；非平滑（无 200ms 释放） |
| 表情用 SDK 内置 `expressionManager.setExpression` | `useLive2D.ts:270` | 阶段3 已实现可用，**本期保留**，不重做 |
| 无自动眨眼兜底（依赖模型/SDK 内置，未受控） | — | 研究文档差距 6 未补 |
| 无 idle 眼动兜底 | — | 研究文档差距 6 未补 |
| 无统一每帧管线，新增表现要散落各处 imperative 写 | — | 研究文档差距 4（阶段4）核心目标 |

**结论**：把"每帧要写的参数"统一收敛到一个**在 SDK update 之后执行**的插件链，保证我们的最终参数不被覆盖，并补齐眨眼/眼动兜底。

---

## 2. 目标与非目标

**做（本期）：**
- 定义 `Live2DFramePlugin` 类型 + 一个**在 SDK `motionManager.update` 之后**执行的插件运行器（hook 方式，参考 AIRI）。
- 三个内置插件：
  1. **lipSync**：每帧把目标 mouthOpen（带平滑释放）写入 `ParamMouthOpenY`。
  2. **autoBlink**：受控自动眨眼，写 `ParamEyeLOpen/ParamEyeROpen`；同时**禁用 SDK 内置 eyeBlink** 避免互相打架。
  3. **idleEyeFocus**：无外部 focus / 不说话时，做轻微眼神漂移（`ParamEyeBallX/Y`）。
- 插件可通过 env / 参数开关，向后兼容（默认开 lipSync + autoBlink，idleEyeFocus 默认开但可关）。
- `dispose` 时还原 hook 与 SDK eyeBlink，清理 ticker/状态。

**不做（登记后续）：**
- 自研 expression controller（读 exp3、Add/Multiply/Overwrite blend、auto-reset）——阶段3 已用 SDK 内置，本期不替换（见 §7 权衡）。
- beat sync（节拍驱动头部）——AIRI 有，AsukaBot 无音乐场景，跳过。
- 鼠标坐标眼动接管——`autoInteract` 已提供鼠标 focus，本期只补 idle 兜底，不重写鼠标 focus（见 §7）。
- 表情/动作配置 UI、模型导入校验——研究文档差距 7/8，属另一阶段。

---

## 3. 整体数据流（改动后）

```
store(mouthOpen / speaking / emotion / expressionCommand)
  │  (Stage watch 不变；setMouthOpen 改为"设目标值"而非直接写参数)
  ▼
useLive2D
  ├── mount：Live2DModel.from(autoInteract:true)
  │     ├── 关闭 SDK 内置 eyeBlink（internalModel.eyeBlink = null）
  │     └── hook internalModel.motionManager.update：
  │            原始 update(motion + expression 写参数)
  │            → 依次执行 post 插件（在 SDK 之后写最终参数）：
  │                 lipSync → autoBlink → idleEyeFocus
  │
  └── dispose：还原 update、还原 eyeBlink、清状态
```

关键点：**插件在 SDK update 之后写参数**，所以口型/眨眼/眼动是"最终值"，不会被 motion 曲线覆盖。表情（SDK expressionManager）在原始 update 内写，插件只动 mouth/eye 参数，互不覆盖（眼睑冲突见 §7 风险）。

---

## 4. 新增 / 改动文件

```
frontend/src/
├── composables/
│   ├── live2d/
│   │   └── frame-plugins.ts     # 新：Live2DFramePlugin 类型 + 三个插件工厂（纯函数化，便于测试）
│   └── useLive2D.ts             # 改：mount 后装配插件链、禁用 SDK eyeBlink；setMouthOpen 改为设目标；dispose 还原
└── types/live2d.ts             # 改：导出 Live2DFramePlugin / FrameContext 类型（或置于 frame-plugins.ts）
```

Stage / store 数据接口**不变**（`setMouthOpen` 语义从"立即写参数"变为"设目标值，由 lipSync 插件每帧应用"，对调用方透明）。

---

## 5. 接口设计

### 5.1 帧上下文与插件类型（`frame-plugins.ts`）

```ts
export interface Live2DCoreModel {
  setParameterValueById: (id: string, value: number) => void
  getParameterValueById: (id: string) => number
}

export interface Live2DFrameContext {
  coreModel: Live2DCoreModel
  now: number        // performance.now()，毫秒
  deltaMs: number    // 距上一帧毫秒
}

export type Live2DFramePlugin = (ctx: Live2DFrameContext) => void
```

### 5.2 lipSync 插件

```ts
// 读取共享目标 mouthOpen（getter 注入），每帧平滑后写 ParamMouthOpenY
export function createLipSyncPlugin(getTarget: () => number, opts?: {
  releaseMs?: number   // 说话结束/目标为0时的平滑释放，默认 200ms（对齐 AIRI）
}): Live2DFramePlugin
```
- 目标值来自 `useLive2D` 内部 `mouthTarget`（由 `setMouthOpen` 设置）。
- 平滑：当前值向目标插值；目标降为 0 时按 `releaseMs` 缓释，避免闭嘴突兀。

### 5.3 autoBlink 插件

```ts
export function createAutoBlinkPlugin(opts?: {
  intervalMs?: [number, number]  // 两次眨眼间隔随机区间，默认 [2000, 6000]
  closingMs?: number             // 闭眼时长，默认 100
  openingMs?: number             // 睁眼时长，默认 150
}): Live2DFramePlugin
```
- 内部状态机：idle（睁眼）→ closing → opening → idle，下次触发时间随机。
- 每帧写 `ParamEyeLOpen`/`ParamEyeROpen`（0~1）。
- **前置**：mount 时 `internalModel.eyeBlink = undefined` 关闭 SDK 内置眨眼，避免双写抖动。

### 5.4 idleEyeFocus 插件

```ts
export function createIdleEyeFocusPlugin(getActive: () => boolean, opts?: {
  driftMs?: number     // 每个漂移目标的停留时长，默认 ~3000
  range?: number       // 漂移幅度 0~1，默认 0.3
}): Live2DFramePlugin
```
- `getActive()` 返回 true（说话中或近期有鼠标 focus）时**不漂移**，交还 SDK focus。
- idle 时缓慢插值 `ParamEyeBallX/Y` 到随机小目标，营造自然眼神。

### 5.5 `useLive2D` 装配（改动点）

- mount 成功后：
  - `runtime.model.internalModel.eyeBlink = undefined`（禁用 SDK 眨眼）。
  - 取 `motionManager = internalModel.motionManager`，保存 `originalUpdate = motionManager.update.bind(...)`，替换为包裹版：调用原始 update 后，按序执行 `framePlugins`。
  - 用 `performance.now()` 计算 `deltaMs`。
- 暴露新增（可选）：`setIdleEye(enabled)`；`setMouthOpen` 改为写 `mouthTarget`。
- dispose：还原 `motionManager.update = originalUpdate`、`eyeBlink`，清理状态与定时器。

> Hook `motionManager.update`（而非另起 `app.ticker.add`）的原因：能精确控制"在 SDK 写完参数之后"执行，参数顺序确定，和 AIRI 一致；也无需担心 ticker 优先级竞争。

---

## 6. 参数与开关（env，向后兼容）

| env | 默认 | 作用 |
|---|---|---|
| `VITE_LIVE2D_AUTO_BLINK` | `true` | 关则不接管眨眼（保留 SDK 内置） |
| `VITE_LIVE2D_LIPSYNC_RELEASE_MS` | `200` | 口型缓释时长 |
| `VITE_LIVE2D_IDLE_EYE` | `true` | idle 眼动兜底开关 |

参数名/范围不硬编码到无法覆盖；模型若无对应参数 id，`setParameterValueById` 静默无效，不报错。

---

## 7. 关键权衡与风险

| 决策 | 选择 | 理由 / 代价 |
|---|---|---|
| 表情系统 | **保留 SDK expressionManager**，不自研 exp3 controller | 阶段3 已可用；自研 blend/auto-reset 成本高、收益小 → 登记后续 |
| hook 位置 | **包裹 `motionManager.update`**（post 插件） | 参数顺序确定，最终值不被覆盖；比 `app.ticker` 更可靠 |
| 眼动 | **只补 idle 兜底**，鼠标 focus 仍交 SDK `autoInteract` | 最小改动；不重写坐标换算 |
| 眨眼 | 接管并**禁用 SDK eyeBlink** | 避免双写抖动；代价：需在 dispose 还原 |
| 口型 | 从响应式 watch 改为**插件每帧应用** + 平滑 | 不被 SDK 覆盖、闭嘴更自然 |

**风险点：**
- **眼睑参数冲突**：若某 exp3 表情自身写 `ParamEyeLOpen/ROpen`（如闭眼表情），autoBlink 会在其后覆盖，导致表情"睁眼"。MVP 接受此限制；缓解项（登记后续）：autoBlink 改为对当前值取 min，或表情期间暂停眨眼。
- **参数 id 因模型而异**：Frieren 用标准 Cubism id（`ParamMouthOpenY`/`ParamEyeLOpen`/`ParamEyeROpen`/`ParamEyeBallX`/`ParamEyeBallY`），其它模型可能不同 → 后续做可配置映射。
- **HMR / 重复 mount**：必须在 dispose 严格还原 hook 与 eyeBlink，否则热更后出现双重 update。

---

## 8. 测试与验收

前端当前**无单元测试运行器**（验收以 `pnpm --dir frontend lint`(vue-tsc) + 手动为准，对齐现有 live2d 提交方式）。

- **类型/lint**：`pnpm --dir frontend lint` 无 error。
- **纯函数可测**：插件工厂写成纯函数（输入 ctx，输出对 mock core 的写入序列），若后续引入 vitest 可直接覆盖（本期不强制新增 runner）。
- **手动验收**（参考 `开发启动指南.md` 启动前后端）：
  - ✓ 静止时数字人**自然眨眼**（频率自然，无抖动/常闭）。
  - ✓ TTS 播放时嘴随音频开合，**停止后 ~200ms 平滑闭合**（非突然闭嘴）。
  - ✓ idle 且鼠标不动时，眼神有**轻微自然漂移**；鼠标移动/说话时不抢 focus。
  - ✓ 触发 `[expression:xxx]` 表情仍生效（与插件链共存）。
  - ✓ 切换模型 / HMR 后无双重眨眼、无报错。

---

## 9. 后续登记（不在本期）

- 自研 exp3 expression controller（Add/Multiply/Overwrite blend、持久默认、auto-reset）。
- autoBlink 与表情眼睑参数的协调（min 混合 / 表情期暂停眨眼）。
- 参数 id 按模型可配置映射。
- 鼠标坐标眼动接管（替换 SDK focus，统一 idle/鼠标过渡）。
- 表情/动作配置 UI + 模型导入与 model3.json 结构校验（研究文档差距 7/8）。

---

**本设计已完成。明确了 `Live2DFramePlugin` 类型、hook 位置、三插件接口、env 开关、风险与验收。**

**下一步：等待用户确认本设计后，在 `feat/live2d` 上实现 `frame-plugins.ts` + 改 `useLive2D.ts`，再跑 lint + 手动验收。**
