// REST 封装：对齐后端 main.py / routes/chat.py。默认走 Vite proxy（相对路径）。
import type { GenerateWikiRequest, GenerateWikiResponse } from '@/types/wiki'
import type { LanguageCode } from '@/types/language'
import type { RealtimeSessionResponse, SdpMessage } from '@/types/realtime'

const apiBase = import.meta.env.VITE_API_BASE ?? ''

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const payload = await res.json() as { detail?: string | Array<{ msg?: string }> }
    if (typeof payload.detail === 'string')
      return payload.detail
    if (Array.isArray(payload.detail))
      return payload.detail.map(item => item.msg).filter(Boolean).join('；') || fallback
    return fallback
  }
  catch {
    return fallback
  }
}

export interface HealthResponse {
  status: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${apiBase}/health`)
  if (!res.ok)
    throw new Error(`health ${res.status}`)
  return res.json() as Promise<HealthResponse>
}

export interface ChatResponse {
  reply: string
}

export async function postChat(conversationId: string, message: string): Promise<ChatResponse> {
  const res = await fetch(`${apiBase}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  })
  if (!res.ok)
    throw new Error(`chat ${res.status}`)
  return res.json() as Promise<ChatResponse>
}

export async function generateWiki(
  payload: GenerateWikiRequest,
): Promise<GenerateWikiResponse> {
  const res = await fetch(`${apiBase}/generate_wiki`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok)
    throw new Error(await errorMessage(res, `generate_wiki ${res.status}`))
  return res.json() as Promise<GenerateWikiResponse>
}

export async function postTts(text: string, voice?: string, language?: LanguageCode): Promise<Blob> {
  const res = await fetch(`${apiBase}/api/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, language }),
  })
  if (!res.ok)
    throw new Error(await errorMessage(res, `tts ${res.status}`))
  return res.blob()
}

export async function postTtsStream(text: string, voice?: string, language?: LanguageCode): Promise<Response> {
  const res = await fetch(`${apiBase}/api/tts/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, language }),
  })
  if (!res.ok)
    throw new Error(await errorMessage(res, `tts stream ${res.status}`))
  if (!res.body)
    throw new Error('tts stream response has no body')
  return res
}

export async function createRealtimeSession(
  conversationId: string,
  payload: { persona_id?: string, level?: string, language?: string, voice?: string } = {},
): Promise<RealtimeSessionResponse> {
  const res = await fetch(`${apiBase}/api/realtime/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, ...payload }),
  })
  if (!res.ok)
    throw new Error(await errorMessage(res, `realtime session ${res.status}`))
  return res.json() as Promise<RealtimeSessionResponse>
}

export async function postRealtimeOffer(sessionId: string, offer: SdpMessage): Promise<SdpMessage> {
  const res = await fetch(`${apiBase}/api/realtime/sessions/${sessionId}/offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(offer),
  })
  if (!res.ok)
    throw new Error(await errorMessage(res, `realtime offer ${res.status}`))
  return res.json() as Promise<SdpMessage>
}

export async function closeRealtimeSession(sessionId: string): Promise<void> {
  const res = await fetch(`${apiBase}/api/realtime/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!res.ok && res.status !== 404)
    throw new Error(await errorMessage(res, `realtime close ${res.status}`))
}
