export type EmotionType = 'idle' | 'think' | 'happy' | 'sad'

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

export type Live2DExpressionBlendMode = 'Add' | 'Multiply' | 'Overwrite'

export interface Live2DExpressionParameter {
  parameterId: string
  value: number
  blend: Live2DExpressionBlendMode
}

export interface Live2DExpressionDefinition {
  name: string
  parameters: Live2DExpressionParameter[]
}
