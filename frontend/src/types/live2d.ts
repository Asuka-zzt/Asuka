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

// A visual change (emotion/motion/expression) to apply when its matching speech plays,
// rather than as soon as the control tag is parsed from the token stream.
export interface Live2DVisualCue {
  emotion?: EmotionType
  motion?: string
  expression?: string
  durationMs?: number
  intensity?: number
}
