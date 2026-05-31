// REST 封装：对齐后端 main.py / routes/chat.py。默认走 Vite proxy（相对路径）。
const apiBase = import.meta.env.VITE_API_BASE ?? ''

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
