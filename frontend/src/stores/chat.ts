import type { Message } from '@/types/chat'

import { defineStore } from 'pinia'
import { ref } from 'vue'

function uid(): string {
  return Math.random().toString(36).slice(2, 10)
}

// 会话消息 + 流式拼接状态。WS 收发逻辑在 composables/useChatSocket.ts。
export const useChatStore = defineStore('chat', () => {
  const conversationId = ref(`web-${uid()}`)
  const messages = ref<Message[]>([])
  const sending = ref(false)
  const connected = ref(false)
  let streamingId: string | null = null

  function pushUser(content: string) {
    messages.value.push({ id: uid(), role: 'user', content })
  }

  function startAssistant() {
    const id = uid()
    streamingId = id
    messages.value.push({ id, role: 'assistant', agentId: 'default', content: '', streaming: true })
    sending.value = true
  }

  function current(): Message | undefined {
    return messages.value.find(m => m.id === streamingId)
  }

  function appendToken(token: string): Message | undefined {
    const m = current()
    if (m)
      m.content += token
    return m
  }

  function finalize(): Message | undefined {
    const m = current()
    if (m)
      m.streaming = false
    streamingId = null
    sending.value = false
    return m
  }

  function setError(msg: string) {
    const m = current()
    if (m) {
      m.content += `${m.content ? '\n' : ''}[错误] ${msg}`
      m.streaming = false
    }
    streamingId = null
    sending.value = false
  }

  return { conversationId, messages, sending, connected, pushUser, startAssistant, appendToken, finalize, setError }
})
