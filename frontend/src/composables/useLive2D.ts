import type { Ref } from 'vue'
import type { Application } from '@pixi/app'

import type { Live2DCoreModel, Live2DFramePlugin } from './live2d/frame-plugins'

import { onBeforeUnmount, ref } from 'vue'

import { createAutoBlinkPlugin, createLipSyncPlugin } from './live2d/frame-plugins'

export type Live2DState = 'placeholder' | 'loading' | 'mounted' | 'error'

const DEFAULT_CUBISM_CORE_URL = 'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js'
const DEFAULT_MODEL_SCALE = 1
const DEFAULT_MODEL_OFFSET_X = 0
const DEFAULT_MODEL_OFFSET_Y = 0
const DEFAULT_LIPSYNC_RELEASE_MS = 200

declare global {
  interface Window {
    Live2DCubismCore?: unknown
  }
}

interface Live2DRuntime {
  app?: Application
  model?: {
    width: number
    height: number
    x: number
    y: number
    scale: { set: (x: number, y?: number) => void }
    anchor?: { set: (x: number, y?: number) => void }
    destroy: () => void
    on?: (event: string, handler: (hitAreas: string[]) => void) => void
    motion?: (group: string, index?: number) => unknown
    // pixi-live2d-display loads expressions declared in model3.json and applies them via
    // internalModel.motionManager.expressionManager inside its own per-frame update loop.
    internalModel?: {
      // Built-in eye blink driver; we disable it so our autoBlink plugin can take over.
      eyeBlink?: unknown
      coreModel?: {
        setParameterValueById?: (id: string, value: number) => void
        getParameterValueById?: (id: string) => number
      }
      motionManager?: {
        update?: (model: object, now: number) => boolean
        expressionManager?: {
          definitions?: Array<{ Name?: string }>
          setExpression?: (id: string | number) => unknown
          resetExpression?: () => void
        }
      }
    }
  }
  modelSize?: { width: number, height: number }
  resizeObserver?: ResizeObserver
  // Pending timer that clears a timed expression back to neutral.
  expressionResetTimer?: ReturnType<typeof setTimeout>
  // Per-frame plugin chain run after the SDK's motionManager.update.
  framePlugins?: Live2DFramePlugin[]
  originalMotionUpdate?: (model: object, now: number) => boolean
  lastFrameNow?: number
  // Target ParamMouthOpenY consumed each frame by the lipSync plugin.
  mouthTarget?: number
}

function containerSize(container: HTMLElement) {
  const rect = container.getBoundingClientRect()
  return {
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
  }
}

function envNumber(value: string | undefined, fallback: number) {
  if (!value)
    return fallback

  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function envBool(value: string | undefined, fallback: boolean) {
  if (value === undefined || value === '')
    return fallback
  return value !== 'false' && value !== '0'
}

function fitModel(runtime: Live2DRuntime, container: HTMLElement) {
  if (!runtime.model || !runtime.app)
    return

  const { width, height } = containerSize(container)
  runtime.app.renderer.resize(width, height)

  const modelWidth = Math.max(1, runtime.modelSize?.width ?? runtime.model.width)
  const modelHeight = Math.max(1, runtime.modelSize?.height ?? runtime.model.height)
  const modelScale = envNumber(import.meta.env.VITE_LIVE2D_MODEL_SCALE, DEFAULT_MODEL_SCALE)
  const offsetX = envNumber(import.meta.env.VITE_LIVE2D_MODEL_OFFSET_X, DEFAULT_MODEL_OFFSET_X)
  const offsetY = envNumber(import.meta.env.VITE_LIVE2D_MODEL_OFFSET_Y, DEFAULT_MODEL_OFFSET_Y)
  const scale = Math.min((width * 0.82) / modelWidth, (height * 0.92) / modelHeight) * modelScale

  runtime.model.scale.set(scale)
  runtime.model.x = width * (0.5 + offsetX)
  runtime.model.y = height * (0.5 + offsetY)
}

interface FramePluginOptions {
  autoBlink: boolean
  lipSyncReleaseMs: number
}

function buildFramePlugins(runtime: Live2DRuntime, options: FramePluginOptions): Live2DFramePlugin[] {
  const plugins: Live2DFramePlugin[] = [
    createLipSyncPlugin(() => runtime.mouthTarget ?? 0, { releaseMs: options.lipSyncReleaseMs }),
  ]
  if (options.autoBlink)
    plugins.push(createAutoBlinkPlugin())
  return plugins
}

// Wrap the SDK's motionManager.update so our plugins write the final mouth/eye
// params each frame, after the SDK has applied motions and expressions.
function installFramePlugins(runtime: Live2DRuntime, options: FramePluginOptions): void {
  const internal = runtime.model?.internalModel
  const motionManager = internal?.motionManager
  const coreModel = internal?.coreModel
  if (!internal || typeof motionManager?.update !== 'function')
    return
  if (typeof coreModel?.setParameterValueById !== 'function' || typeof coreModel.getParameterValueById !== 'function')
    return

  // Disable the SDK's built-in eye blink so autoBlink owns the eye-open params.
  if (options.autoBlink)
    internal.eyeBlink = undefined

  const core = coreModel as Live2DCoreModel
  const plugins = buildFramePlugins(runtime, options)
  const original = motionManager.update.bind(motionManager)

  runtime.framePlugins = plugins
  runtime.originalMotionUpdate = original
  runtime.lastFrameNow = undefined

  motionManager.update = (model: object, now: number): boolean => {
    const result = original(model, now)
    const deltaMs = runtime.lastFrameNow === undefined ? 0 : Math.max(0, now - runtime.lastFrameNow)
    runtime.lastFrameNow = now
    const ctx = { coreModel: core, now, deltaMs }
    for (const plugin of plugins)
      plugin(ctx)
    return result
  }
}

function restoreFramePlugins(runtime: Live2DRuntime): void {
  const motionManager = runtime.model?.internalModel?.motionManager
  if (motionManager && runtime.originalMotionUpdate)
    motionManager.update = runtime.originalMotionUpdate
  runtime.originalMotionUpdate = undefined
  runtime.framePlugins = undefined
  runtime.lastFrameNow = undefined
  runtime.mouthTarget = 0
}

export function useLive2D(container: Ref<HTMLDivElement | undefined>) {
  const state = ref<Live2DState>('placeholder')
  const error = ref('')
  const expressionNames = ref<string[]>([])
  const runtime: Live2DRuntime = {}
  const framePluginOptions: FramePluginOptions = {
    autoBlink: envBool(import.meta.env.VITE_LIVE2D_AUTO_BLINK, true),
    lipSyncReleaseMs: envNumber(import.meta.env.VITE_LIVE2D_LIPSYNC_RELEASE_MS, DEFAULT_LIPSYNC_RELEASE_MS),
  }
  let mountToken = 0
  let cubismCorePromise: Promise<void> | undefined

  function ensureCubismCore(): Promise<void> {
    if (window.Live2DCubismCore)
      return Promise.resolve()

    if (cubismCorePromise)
      return cubismCorePromise

    const coreUrl = import.meta.env.VITE_LIVE2D_CUBISM_CORE_URL ?? DEFAULT_CUBISM_CORE_URL
    cubismCorePromise = new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>('script[data-live2d-cubism-core]')
      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true })
        existing.addEventListener('error', () => reject(new Error('Cubism Core 加载失败')), { once: true })
        return
      }

      const script = document.createElement('script')
      script.src = coreUrl
      script.async = true
      script.dataset.live2dCubismCore = 'true'
      script.addEventListener('load', () => resolve(), { once: true })
      script.addEventListener('error', () => reject(new Error(`Cubism Core 加载失败：${coreUrl}`)), { once: true })
      document.head.appendChild(script)
    })

    return cubismCorePromise
  }

  async function mount(modelUrl: string): Promise<void> {
    const target = container.value
    const url = modelUrl.trim()
    if (!target || !url) {
      state.value = 'placeholder'
      return
    }

    dispose()
    const token = ++mountToken
    state.value = 'loading'
    error.value = ''

    try {
      await ensureCubismCore()

      const [
        { Application },
        { extensions },
        { Ticker, TickerPlugin },
        { Live2DModel },
      ] = await Promise.all([
        import('@pixi/app'),
        import('@pixi/extensions'),
        import('@pixi/ticker'),
        import('pixi-live2d-display/cubism4'),
      ])

      if (token !== mountToken)
        return

      Live2DModel.registerTicker(Ticker)
      extensions.add(TickerPlugin)

      const { width, height } = containerSize(target)
      const app = new Application({
        width,
        height,
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
      })

      app.view.className = 'live2d-canvas'
      app.view.style.width = '100%'
      app.view.style.height = '100%'
      app.view.style.display = 'block'
      app.view.style.objectFit = 'contain'
      target.appendChild(app.view)

      const model = await Live2DModel.from(url, { autoInteract: true })
      if (token !== mountToken) {
        model.destroy()
        app.destroy(true)
        return
      }

      model.anchor?.set(0.5, 0.5)
      model.on?.('hit', (hitAreas: string[]) => {
        if (hitAreas.includes('body'))
          model.motion?.('tap_body')
      })

      app.stage.addChild(model)
      runtime.app = app
      runtime.model = model
      runtime.modelSize = {
        width: Math.max(1, model.width),
        height: Math.max(1, model.height),
      }
      expressionNames.value = expressionNamesOf(runtime)
      installFramePlugins(runtime, framePluginOptions)
      fitModel(runtime, target)

      runtime.resizeObserver = new ResizeObserver(() => fitModel(runtime, target))
      runtime.resizeObserver.observe(target)
      state.value = 'mounted'
    }
    catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      dispose()
      state.value = 'error'
    }
  }

  function dispose(): void {
    mountToken += 1
    restoreFramePlugins(runtime)
    runtime.resizeObserver?.disconnect()
    runtime.resizeObserver = undefined

    if (runtime.expressionResetTimer) {
      clearTimeout(runtime.expressionResetTimer)
      runtime.expressionResetTimer = undefined
    }
    expressionNames.value = []

    if (runtime.model && runtime.app) {
      try {
        runtime.app.stage.removeChild(runtime.model as never)
      }
      catch {
        // Pixi may already have removed the child during HMR or teardown.
      }
    }

    runtime.model?.destroy()
    runtime.model = undefined
    runtime.modelSize = undefined

    runtime.app?.ticker?.stop()
    runtime.app?.destroy(true)
    runtime.app = undefined
  }

  function playMotion(group: string, index?: number, fallbackGroups: string[] = []): boolean {
    if (!runtime.model?.motion)
      return false

    for (const candidate of [group, ...fallbackGroups]) {
      try {
        runtime.model.motion(candidate, index)
        return true
      }
      catch (e) {
        console.warn(`[live2d] motion "${candidate}" failed:`, e)
      }
    }

    return false
  }

  function setParameter(parameterId: string, value: number): void {
    runtime.model?.internalModel?.coreModel?.setParameterValueById?.(parameterId, value)
  }

  function setMouthOpen(value: number): void {
    const clamped = Math.min(1, Math.max(0, value))
    runtime.mouthTarget = clamped
    // Fallback for when the per-frame plugin chain failed to install.
    if (!runtime.framePlugins)
      setParameter('ParamMouthOpenY', clamped)
  }

  function clearExpressionTimer(): void {
    if (runtime.expressionResetTimer) {
      clearTimeout(runtime.expressionResetTimer)
      runtime.expressionResetTimer = undefined
    }
  }

  function setExpression(name: string, durationMs?: number): boolean {
    const manager = runtime.model?.internalModel?.motionManager?.expressionManager
    const target = name.trim()
    if (!manager?.setExpression || !expressionNames.value.includes(target))
      return false

    clearExpressionTimer()
    manager.setExpression(target)
    if (durationMs && durationMs > 0)
      runtime.expressionResetTimer = setTimeout(resetExpression, durationMs)
    return true
  }

  function resetExpression(): void {
    clearExpressionTimer()
    runtime.model?.internalModel?.motionManager?.expressionManager?.resetExpression?.()
  }

  onBeforeUnmount(dispose)

  return {
    state,
    error,
    expressionNames,
    mount,
    dispose,
    playMotion,
    setParameter,
    setMouthOpen,
    setExpression,
    resetExpression,
  }
}

// Names of the expressions pixi-live2d-display loaded from model3.json's FileReferences.Expressions.
function expressionNamesOf(runtime: Live2DRuntime): string[] {
  const defs = runtime.model?.internalModel?.motionManager?.expressionManager?.definitions ?? []
  return defs.map(def => (def.Name ?? '').trim()).filter(Boolean)
}
