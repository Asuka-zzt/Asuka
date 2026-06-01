import type { WsEvent } from '@/types/chat'

import { onBeforeUnmount, onMounted } from 'vue'

import { useChatStore } from '@/stores/chat'

// 封装 /ws/{conversation_id}：连接、流式 token、基础重连。
// 在组件 setup 中调用一次（ChatPanel），返回 send()。
export function useChatSocket() {
  const store = useChatStore()
  let ws: WebSocket | null = null
  let retry = 0
  let closedByUser = false

  function wsUrl(): string {
    const base = import.meta.env.VITE_WS_BASE
      ?? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
    return `${base}/ws/${store.conversationId}`
  }

  function connect() {
    ws = new WebSocket(wsUrl())
    ws.onopen = () => {
      store.connected = true
      retry = 0
    }
    ws.onclose = () => {
      store.connected = false
      if (!closedByUser) {
        retry += 1
        setTimeout(connect, Math.min(5000, 500 * retry))
      }
    }
    ws.onmessage = (e: MessageEvent) => {
      const data = JSON.parse(e.data as string) as WsEvent
      if (data.type === 'token')
        store.appendToken(data.content)
      else if (data.type === 'done')
        store.finalize()
      else if (data.type === 'error')
        store.setError(data.content)
    }
  }

  function send(text: string) {
    const t = text.trim()
    if (!t)
      return
    store.pushUser(t)
    store.startAssistant()
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ message: t }))
    else
      store.setError('未连接到服务端')
  }

  onMounted(connect)
  onBeforeUnmount(() => {
    closedByUser = true
    ws?.close()
  })

  return { send }
}
