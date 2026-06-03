# Live2D 表情功能调试记录

> 记录一次完整的「数字人表情无法触发」排查 → 修复全过程。
> 时间：2026-06（feat/live2d 分支）。模型：Frieren（VTube Studio 导出的 Cubism 4 模型）。
> 技术栈：前端 pixi-live2d-display + Pixi 6；后端 FastAPI WebSocket 流式 + DeepSeek。

---

## 0. 初始现象

用户报告：**模型完全不做表情**，前端 console 报错：

```
expression-controller.ts:90 [live2d] expression "bl" failed to load:
  SyntaxError: Unexpected token '<', "<!doctype "... is not valid JSON
expression-controller.ts:90 [live2d] expression "anyazZZ" failed to load: ...
```

最终定位到**四个相互独立的问题**，逐个修复。整条链路是：

```
用户输入 → ChatPanel → useChatSocket(WS) → ws.py → LangGraph Agent → LLM
  → LLM 在回复里输出 [emotion:xx]/[expression:xx] 控制标签
  → ws.py Live2DTagExtractor 流式提取标签 → 发 live2d.emotion 事件
  → useChatSocket → live2d store → Live2DStage watch → useLive2D.setExpression
  → pixi-live2d-display expressionManager → 模型渲染表情
```

---

## 1. 调试方法论：用真实浏览器自动化驱动

Live2D 是 WebGL 渲染，光看代码无法判断"参数到底有没有应用到画面"。本次排查的核心手段是
**用 Playwright 驱动机器上缓存的 Chromium（headless + swiftshader 软件 WebGL）跑真实前端**，做到：

- `page.evaluate()` 进页面直接调用真实模型对象、读 Cubism 参数值；
- 给 `applyFrame` / `setParameterValueById` 打桩计数，证明"调用了但没生效"；
- `page.screenshot({clip})` 截脸部，用 pngjs 做像素差，量化每个表情的可见度；
- 直连后端 WebSocket（Python websockets）发消息，抓取后端真实下发的事件流。

> 关键经验：**参数读回值不可信**（见 §3 的 `loadParameters`），最终判据是
> **截图 + 肉眼/像素差**，以及**直连 WS 抓事件**。

---

## 2. Bug ①：表情文件 404 被 SPA 兜底页污染 → JSON 解析报错

**现象**：`bl`、`anyazZZ` 两个表情加载报 `Unexpected token '<'`。

**根因**：`Frieren.model3.json` 声明了 14 个表情，但磁盘上只有 12 个 `.exp3.json`。
缺失的 `bl.exp3.json` / `anyazZZ.exp3.json` 被 Vite 开发服务器用 **SPA 兜底页 `index.html`
（`<!doctype html>…`，HTTP 200）** 应答。代码 `res.ok` 检查通过，`res.json()` 拿 HTML 解析 → 报错。

**证据**：`unzip -l Frieren.zip` 确认原始 zip 里**本来就没有**这两个文件 —— 原作者的
model3.json 就是悬空引用。

**修复**：从 `Frieren.model3.json` 删除两个悬空引用；并修正 `"erd "` 的尾随空格
（库按 `def.Name === name` 精确匹配，否则 LLM 发的 `erd` 永远匹配不上）。

---

## 3. Bug ②：自研表情控制器与渲染管线打架 → 表情完全不渲染

修掉报错后，12 个表情能加载，但**画面依然不动**。

**排查过程**：

1. Playwright 调 `controller.set('ku')` 返回 `true`，但读 `getParameterValueById('Param11')` 始终为 `0`。
2. 给 `applyFrame` / `setParameterValueById` 打桩：证明每帧都写了 `Param11 = 30`（写了 8 次），
   但读回来还是 `0`。
3. 翻 `pixi-live2d-display/dist/cubism4.js` 的 `Cubism4InternalModel.update()`：

   ```
   motionManager.update()      // motion 写参数
   saveParameters()            // 快照
   ... physics / pose ...
   emit("beforeModelUpdate")
   model.update()              // 提交渲染
   model.loadParameters()      // 用快照覆盖回去 ← 把写入抹掉
   ```

**根因**：自研 `Live2DExpressionController` 把 `applyFrame()` 挂在 `app.ticker` 上，作为
**独立回调**运行，与模型自身的更新循环（`registerTicker(Ticker)` 驱动）**时序错位**。
参数要么被 motion 覆盖，要么在 `model.update()` 提交之后才写、随即被 `loadParameters()` 抹掉。

**修复（关键决策）**：**删除自研控制器**，改用 pixi-live2d-display **自带的
`internalModel.motionManager.expressionManager`**。库已经从 model3.json 自动加载了全部表情，
并在更新循环的正确位置（`saveParameters` 之后、`loadParameters` 之前）用 `CubismExpressionMotion`
做正确的叠加混合。符合「框架优先，不重造」。

- `useLive2D.setExpression(name)` → `expressionManager.setExpression(name)`；
- `resetExpression()` → `expressionManager.resetExpression()`；
- 表情名从 `expressionManager.definitions` 读；`durationMs` 用 `setTimeout` 自动复位；
- 删除 `frontend/src/live2d/expression-controller.ts` 及其专用类型。

**验证**：Playwright 截图，`set('anya2')` → 眼睛明显变成笑弯 `^‿^`，定时复位也正常。

---

## 4. Bug ③：流式标签提取器在分片边界丢标签 → 对话永远收不到事件

手动 `set()` 能出表情了，但**正常聊天依然不触发**，前端 console 一个 `live2d.emotion` 都没有。

**排查过程**：直连后端 WS 发消息，抓到决定性证据 —— LLM **完全正确地**输出了
`[expression:ku]` 等标签，但后端 `live2d.emotion` 事件数 = **0**，而且"清理后的文本"里
**还残留原始标签**。说明 `Live2DTagExtractor` 没提取。

**隔离复现**：把同一段文本**逐字符**喂给提取器 → 0 事件、标签漏出；**整段一次**喂入 → 正常 3 事件。
LLM 是逐字流式输出的，所以走的正是失败路径。

**根因**：`feed()` 判断"半个标签"时，只在 `rest` 已经是完整 `[emotion:` / `[expression:`
前缀时才缓冲等待。当分片正好切在标签中间（buffer 只剩 `[` 或 `[exp`）时判断为假，于是把 `[`
当普通字符吐出并跳过，标签被永久打断。

**修复**：新增 `_maybe_incomplete_tag()` —— 只要 `rest` **可能**还能补全成标签
（是某标签开头的前缀，或已含完整开头但 `]` 未到），就继续缓冲。并修正 break 时 `i = tag_start`
避免已输出的干净文字被重复保留。

**回归测试**：`tests/test_routes/test_live2d_tag_extractor.py`（6 个用例：逐字符 / 对抗性分片 /
字面方括号 `arr[0]` / 未知标签 / 非法 emotion / 结尾半标签）。

**验证**：直连 WS 多轮对话，每轮都正确下发 `live2d.emotion` 事件；浏览器端到端确认 console
出现事件、模型同步变表情。

> 附带修复（前端，配合表情链路）：`useChatSocket` 对 `live2d.emotion` 事件守卫
> `if (data.emotion)`，使**纯表情事件**（无 emotion 字段）不再调用 `setEmotion(undefined)`；
> `chat.ts` 把 `emotion` 改为可选；`chat.py` 复用提取器剥离 `/chat` 同步接口的标签。

---

## 5. 排查④（非 Bug）：模型自身绑定不均 → 收窄可用表情清单

链路全通后，用户反馈：**只有 `mmy` 等少数表情看得见，`ku`/`han` 等"没反应"**。

**排查过程**：

- `probe()` 直接 await 库的 `setExpression`：12 个表情**全部** `loaded: ok` + `setReturned: true`，
  exp3 文件全是 200 + 合法 JSON。→ 应用层没问题。
- 冻结模型（停 motion + 关眨眼）逐个截图肉眼对比：`mmy`(眯眼)/`anya`/`anya2`(笑眼)/`W`(w嘴)/
  `lks`(张嘴)/`wh`(头顶问号) **有可见效果**；`ku`(哭)/`yy`(晕)/`han`(汗)/`d`(抖)/`zx`/`erd`
  **画面与中性完全一致**（之前的像素差是头发物理抖动噪声）。
- `unzip` 解压 `Frieren.zip` 与 `public/` **逐字节对比**：`moc3` / `cdi3` / 全部 `exp3`
  **完全一致**。→ 不是文件放错。

**结论**：`ku`/`yy`/`han` 对应的自定义参数（Param11哭 / Param16晕 / Param17汗）在这个 **moc3 里
没有绑定可见网格变形** —— 作者在 cdi3 里起了名，但没做出对应图层（或需 VTube Studio 方式才能触发）。
这是模型自带的"半成品"参数，非代码问题。

**处理**：把**可用表情清单收窄成 6 个有可见效果的**：`mmy / anya / anya2 / W / lks / wh`。
同步三处：`Frieren.model3.json`（前端只加载/校验这 6 个）、`model.py`（LLM prompt 清单 + 示例）、
`ws.py`（文档字符串）。LLM 从此只会挑得出可见的表情。

---

## 6. 最终改动清单

| 文件 | 改动 |
|------|------|
| `asuka/routes/ws.py` | **核心修复**：流式标签提取器分片处理（`_maybe_incomplete_tag`）；表情清单文档同步 |
| `asuka/routes/chat.py` | `/chat` 同步接口复用提取器剥离标签 |
| `asuka/core/agent/model.py` | LLM 人格 prompt 的表情清单收窄为 6 个并加语义说明，示例同步 |
| `frontend/src/composables/useLive2D.ts` | 改用库自带 `expressionManager`，删除自研 ticker/hook |
| `frontend/src/live2d/expression-controller.ts` | **删除**（自研轮子，与渲染管线冲突） |
| `frontend/src/composables/useChatSocket.ts` | 纯表情事件守卫，不再 `setEmotion(undefined)` |
| `frontend/src/components/stage/Live2DStage.vue` | `setExpression` 去掉库不支持的 `intensity` 参数 |
| `frontend/src/types/{live2d,chat}.ts` | 删除自研控制器专用类型；`emotion` 改可选 |
| `frontend/public/live2d/Frieren/Frieren.model3.json` | 删 2 个悬空引用 + 修 `erd ` 空格 + 收窄到 6 个可见表情 |
| `tests/test_routes/test_live2d_tag_extractor.py` | **新增** 6 个流式提取回归测试 |

## 7. 验收

- 后端：`ruff` 通过、`pytest` 全绿（含新增 6 个用例）。
- 前端：`vue-tsc` 通过、`vite build` 通过。
- 端到端：直连 WS 多轮对话每轮下发事件；浏览器聊天，LLM 选用的表情均有可见效果。

## 8. 留给后续的经验

1. **Live2D 调试靠截图，不靠读参数**：`saveParameters/loadParameters` 会让参数读回值失真。
2. **框架自带的能力优先复用**：pixi-live2d-display 已内置完整表情系统，自研控制器只会和管线打架。
3. **流式解析必须考虑分片边界**：任何"找特定标记再处理"的增量解析，都要处理标记被切成两半的情况，
   并写逐字符喂入的回归测试。
4. **VTube Studio 导出的模型，cdi3 里有名字 ≠ 有可见绑定**：上线前应逐个验证表情的可见效果，
   只把"看得见"的暴露给 LLM。
