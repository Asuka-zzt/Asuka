import type { EmotionType } from './live2d'
import type { LanguageToolResult } from './language'

export type Role = 'user' | 'assistant'

export interface Message {
  id: string
  role: Role
  agentId?: string // 预留多人格；当前恒为 'default'
  content: string
  streaming?: boolean
  toolResults?: LanguageToolResult[]
}

// 后端 WS 事件（见 routes/ws.py）
export type WsEvent =
  | { type: 'token', content: string }
  | { type: 'tool.result', name: string, payload: unknown }
  | { type: 'done' }
  | { type: 'error', content: string }
  | {
    type: 'live2d.emotion'
    emotion?: EmotionType
    motion?: string
    expression?: string
    durationMs?: number
    intensity?: number
  }

export interface AgentInfo {
  id: string
  name: string
  soul: string
  modelId: string
}
