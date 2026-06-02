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
