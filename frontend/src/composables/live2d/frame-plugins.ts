// Per-frame Live2D parameter pipeline (research doc 阶段4: 插件化 motion update).
// Plugins run AFTER the SDK's motionManager.update each frame, so the values they
// write (mouth / eyes) are the final ones and are not overwritten by motion curves.

export interface Live2DCoreModel {
  setParameterValueById: (id: string, value: number) => void
  getParameterValueById: (id: string) => number
}

export interface Live2DFrameContext {
  coreModel: Live2DCoreModel
  now: number // performance timestamp in ms (as passed to motionManager.update)
  deltaMs: number // ms elapsed since the previous frame
}

export type Live2DFramePlugin = (ctx: Live2DFrameContext) => void

const PARAM_MOUTH_OPEN_Y = 'ParamMouthOpenY'
const PARAM_EYE_L_OPEN = 'ParamEyeLOpen'
const PARAM_EYE_R_OPEN = 'ParamEyeROpen'

function clamp01(value: number): number {
  if (!Number.isFinite(value))
    return 0
  return Math.min(1, Math.max(0, value))
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

// Writes ParamMouthOpenY from a shared target each frame: opens immediately for
// responsiveness, releases smoothly over `releaseMs` so the mouth never snaps shut.
export function createLipSyncPlugin(
  getTarget: () => number,
  opts: { releaseMs?: number } = {},
): Live2DFramePlugin {
  const releaseMs = opts.releaseMs ?? 200
  let current = 0

  return ({ coreModel, deltaMs }) => {
    const target = clamp01(getTarget())
    if (target >= current) {
      current = target
    }
    else {
      const step = releaseMs > 0 ? deltaMs / releaseMs : 1
      current = Math.max(target, current - step)
    }
    coreModel.setParameterValueById(PARAM_MOUTH_OPEN_Y, current)
  }
}

// Controlled auto-blink state machine writing ParamEyeLOpen/ParamEyeROpen.
// The SDK's built-in eyeBlink must be disabled by the caller to avoid double-writes.
export function createAutoBlinkPlugin(
  opts: {
    intervalMs?: [number, number]
    closingMs?: number
    openingMs?: number
  } = {},
): Live2DFramePlugin {
  const [minInterval, maxInterval] = opts.intervalMs ?? [2000, 6000]
  const closingMs = opts.closingMs ?? 100
  const openingMs = opts.openingMs ?? 150

  let phase: 'idle' | 'closing' | 'opening' = 'idle'
  let timer = 0
  let nextBlink = randomBetween(minInterval, maxInterval)
  let open = 1

  return ({ coreModel, deltaMs }) => {
    timer += deltaMs

    if (phase === 'idle') {
      open = 1
      if (timer >= nextBlink) {
        phase = 'closing'
        timer = 0
      }
    }
    else if (phase === 'closing') {
      const t = closingMs > 0 ? Math.min(1, timer / closingMs) : 1
      open = 1 - t
      if (t >= 1) {
        phase = 'opening'
        timer = 0
      }
    }
    else {
      const t = openingMs > 0 ? Math.min(1, timer / openingMs) : 1
      open = t
      if (t >= 1) {
        phase = 'idle'
        timer = 0
        nextBlink = randomBetween(minInterval, maxInterval)
      }
    }

    coreModel.setParameterValueById(PARAM_EYE_L_OPEN, open)
    coreModel.setParameterValueById(PARAM_EYE_R_OPEN, open)
  }
}
