export interface RealtimeSessionResponse {
  session_id: string
  conversation_id: string
  expires_in: number
}

export interface SdpMessage {
  sdp: string
  type: 'offer' | 'answer'
}

export interface RealtimeEvent<T = Record<string, unknown>> {
  type: string
  id: string
  conversationId: string
  sessionId: string
  turnId?: string
  createdAt: number
  payload: T
}

export type VoiceState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'speaking'
  | 'error'

