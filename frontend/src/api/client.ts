// REST 封装：对齐后端 main.py / routes/chat.py。默认走 Vite proxy（相对路径）。
import type { GenerateWikiRequest, GenerateWikiResponse } from '@/types/wiki'

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
