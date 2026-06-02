import type { Ref } from 'vue'
import type { Application } from '@pixi/app'

import { onBeforeUnmount, ref } from 'vue'

export type Live2DState = 'placeholder' | 'loading' | 'mounted' | 'error'

const DEFAULT_CUBISM_CORE_URL = 'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js'
const DEFAULT_MODEL_SCALE = 1
const DEFAULT_MODEL_OFFSET_X = 0
const DEFAULT_MODEL_OFFSET_Y = 0

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
    internalModel?: {
      coreModel?: {
        setParameterValueById?: (id: string, value: number) => void
      }
    }
  }
  modelSize?: { width: number, height: number }
  resizeObserver?: ResizeObserver
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

export function useLive2D(container: Ref<HTMLDivElement | undefined>) {
  const state = ref<Live2DState>('placeholder')
  const error = ref('')
  const runtime: Live2DRuntime = {}
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
    runtime.resizeObserver?.disconnect()
    runtime.resizeObserver = undefined

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
    setParameter('ParamMouthOpenY', Math.min(1, Math.max(0, value)))
  }

  onBeforeUnmount(dispose)

  return { state, error, mount, dispose, playMotion, setParameter, setMouthOpen }
}
