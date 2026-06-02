import type { WsEvent } from '@/types/chat'
import type { EmotionType } from '@/types/live2d'

import { onBeforeUnmount, onMounted } from 'vue'

import { useTtsAudio } from '@/composables/useTtsAudio'
import { useChatStore } from '@/stores/chat'
import { useLive2DStore } from '@/stores/live2d'

const EMOTION_TAG_RE = /\[emotion:(idle|think|happy|sad)\]\s*$/i

function parseEmotion(content: string): { content: string, emotion: EmotionType } {
  const match = content.match(EMOTION_TAG_RE)
  if (!match)
    return { content, emotion: 'idle' }

  return {
    content: content.slice(0, match.index).trimEnd(),
    emotion: match[1].toLowerCase() as EmotionType,
  }
}

// 封装 /ws/{conversation_id}：连接、流式 token、基础重连。
// 在组件 setup 中调用一次（ChatPanel），返回 send()。
export function useChatSocket() {
  const store = useChatStore()
  const live2d = useLive2DStore()
  const tts = useTtsAudio()
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
      if (data.type === 'token') {
        store.appendToken(data.content)
        tts.feedToken(data.content)
      }
      else if (data.type === 'done') {
        const message = store.finalize()
        if (message?.content) {
          const parsed = parseEmotion(message.content)
          message.content = parsed.content
          tts.flush(parsed.emotion)
        }
        else {
          live2d.setEmotion('idle')
        }
      }
      else if (data.type === 'error') {
        store.setError(data.content)
        tts.stop()
      }
      else if (data.type === 'live2d.emotion') {
        live2d.setEmotion(
          data.emotion,
          data.motion ? { group: data.motion } : undefined,
        )
      }
    }
  }

  function send(text: string) {
    const t = text.trim()
    if (!t)
      return
    store.pushUser(t)
    tts.stop()
    live2d.setThinking()
    store.startAssistant()
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ message: t }))
    else {
      store.setError('未连接到服务端')
      live2d.setEmotion('idle')
    }
  }

  onMounted(connect)
  onBeforeUnmount(() => {
    closedByUser = true
    ws?.close()
  })

  return { send }
}
