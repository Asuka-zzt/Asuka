import type {
  Live2DExpressionBlendMode,
  Live2DExpressionDefinition,
  Live2DExpressionParameter,
} from '@/types/live2d'

interface CoreModelAdapter {
  getParameterValueById?: (id: string) => number
  setParameterValueById?: (id: string, value: number) => void
}

interface Model3ExpressionRef {
  Name: string
  File: string
}

interface Model3Json {
  FileReferences?: {
    Expressions?: Model3ExpressionRef[]
  }
}

interface Exp3Json {
  Parameters?: Array<{
    Id?: string
    Value?: number
    Blend?: string
  }>
}

interface ActiveExpression {
  definition: Live2DExpressionDefinition
  intensity: number
  expiresAt?: number
}

function expressionUrl(modelUrl: string, file: string): string {
  return new URL(file, new URL(modelUrl, location.href)).toString()
}

function normalizeBlend(blend: string | undefined): Live2DExpressionBlendMode {
  if (blend === 'Add' || blend === 'Multiply')
    return blend
  return 'Overwrite'
}

function parseExpression(name: string, exp3: Exp3Json): Live2DExpressionDefinition {
  const parameters: Live2DExpressionParameter[] = []
  for (const param of exp3.Parameters ?? []) {
    if (!param.Id || typeof param.Value !== 'number')
      continue
    parameters.push({
      parameterId: param.Id,
      value: param.Value,
      blend: normalizeBlend(param.Blend),
    })
  }
  return { name, parameters }
}

export class Live2DExpressionController {
  private readonly definitions = new Map<string, Live2DExpressionDefinition>()
  private readonly defaults = new Map<string, number>()
  private readonly activeParameterIds = new Set<string>()
  private active?: ActiveExpression

  constructor(private readonly coreModel: CoreModelAdapter) {}

  get names(): string[] {
    return Array.from(this.definitions.keys())
  }

  async load(modelUrl: string, settingsJson: Model3Json): Promise<string[]> {
    const refs = settingsJson.FileReferences?.Expressions ?? []
    for (const ref of refs) {
      const name = ref.Name.trim()
      if (!name || !ref.File)
        continue

      try {
        const res = await fetch(expressionUrl(modelUrl, ref.File))
        if (!res.ok)
          throw new Error(`HTTP ${res.status}`)
        const exp3 = await res.json() as Exp3Json
        const definition = parseExpression(name, exp3)
        if (definition.parameters.length)
          this.definitions.set(name, definition)
      }
      catch (err) {
        console.warn(`[live2d] expression "${name}" failed to load:`, err)
      }
    }

    return this.names
  }

  set(name: string, durationMs?: number, intensity = 1): boolean {
    const definition = this.definitions.get(name.trim())
    if (!definition)
      return false

    this.resetActiveParameters()
    this.active = {
      definition,
      intensity: Math.min(1, Math.max(0, intensity)),
      expiresAt: durationMs && durationMs > 0 ? performance.now() + durationMs : undefined,
    }
    return true
  }

  reset(): void {
    this.resetActiveParameters()
    this.active = undefined
  }

  applyFrame(): void {
    if (!this.active)
      return

    if (this.active.expiresAt && performance.now() >= this.active.expiresAt) {
      this.reset()
      return
    }

    const nextParameterIds = new Set<string>()
    for (const param of this.active.definition.parameters) {
      const nextValue = this.computeValue(param, this.active.intensity)
      this.coreModel.setParameterValueById?.(param.parameterId, nextValue)
      nextParameterIds.add(param.parameterId)
    }

    for (const id of this.activeParameterIds) {
      if (!nextParameterIds.has(id))
        this.resetParameter(id)
    }

    this.activeParameterIds.clear()
    for (const id of nextParameterIds)
      this.activeParameterIds.add(id)
  }

  dispose(): void {
    this.reset()
    this.definitions.clear()
    this.defaults.clear()
  }

  private computeValue(param: Live2DExpressionParameter, intensity: number): number {
    const current = this.coreModel.getParameterValueById?.(param.parameterId) ?? 0
    const modelDefault = this.getDefault(param.parameterId, current)

    if (param.blend === 'Add')
      return modelDefault + param.value * intensity
    if (param.blend === 'Multiply')
      return current * (1 + (param.value - 1) * intensity)
    return modelDefault + (param.value - modelDefault) * intensity
  }

  private getDefault(parameterId: string, fallback: number): number {
    if (!this.defaults.has(parameterId))
      this.defaults.set(parameterId, fallback)
    return this.defaults.get(parameterId) ?? fallback
  }

  private resetActiveParameters(): void {
    for (const id of this.activeParameterIds)
      this.resetParameter(id)
    this.activeParameterIds.clear()
  }

  private resetParameter(parameterId: string): void {
    const modelDefault = this.defaults.get(parameterId)
    if (typeof modelDefault === 'number')
      this.coreModel.setParameterValueById?.(parameterId, modelDefault)
  }
}
