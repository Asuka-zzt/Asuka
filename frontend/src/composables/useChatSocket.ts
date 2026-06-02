import type { WsEvent } from '@/types/chat'
import type { EmotionType } from '@/types/live2d'

import { onBeforeUnmount, onMounted } from 'vue'

import { useTtsAudio } from '@/composables/useTtsAudio'
import { useChatStore } from '@/stores/chat'
import { useLive2DStore } from '@/stores/live2d'

const EMOTION_TAG_RE = /\[emotion:(idle|think|happy|sad)\]\s*$/i
const EXPRESSION_TAG_RE = /\[expression:([A-Za-z0-9_. -]+)\]\s*$/i
const DEFAULT_EXPRESSION_DURATION_MS = 1800

function parseVisualTags(content: string): {
  content: string
  emotion: EmotionType
  expression?: string
} {
  let cleanContent = content
  let emotion: EmotionType | undefined
  let expression: string | undefined

  while (true) {
    const expressionMatch = cleanContent.match(EXPRESSION_TAG_RE)
    if (expressionMatch) {
      expression = expressionMatch[1]?.trim() || expression
      cleanContent = cleanContent.slice(0, expressionMatch.index).trimEnd()
      continue
    }

    const emotionMatch = cleanContent.match(EMOTION_TAG_RE)
    if (emotionMatch) {
      emotion = emotionMatch[1]?.toLowerCase() as EmotionType
      cleanContent = cleanContent.slice(0, emotionMatch.index).trimEnd()
      continue
    }

    break
  }

  return {
    content: cleanContent,
    emotion: emotion ?? 'idle',
    expression,
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
        const message = store.appendToken(data.content)
        if (message)
          tts.feedSnapshot(message.content)
      }
      else if (data.type === 'done') {
        const message = store.finalize()
        if (message?.content) {
          const parsed = parseVisualTags(message.content)
          message.content = parsed.content
          if (parsed.expression) {
            live2d.setExpression({
              name: parsed.expression,
              durationMs: DEFAULT_EXPRESSION_DURATION_MS,
            })
          }
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
        if (data.expression) {
          live2d.setExpression({
            name: data.expression,
            durationMs: data.durationMs ?? DEFAULT_EXPRESSION_DURATION_MS,
            intensity: data.intensity,
          })
        }
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
