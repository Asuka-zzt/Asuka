import type { WsEvent } from '@/types/chat'
import type { LanguageToolResult, PersonaId } from '@/types/language'
import type { EmotionType } from '@/types/live2d'

import { onBeforeUnmount, onMounted, watch } from 'vue'

import { useTtsAudio } from '@/composables/useTtsAudio'
import { MODEL_SPEECH_EVENT, type ModelSpeechRequest } from '@/composables/modelSpeech'
import { useChatStore } from '@/stores/chat'
import { useLive2DStore } from '@/stores/live2d'

const EMOTION_TAG_RE = /\[emotion:(idle|think|happy|sad)\]\s*$/i
const EXPRESSION_TAG_RE = /\[expression:([A-Za-z0-9_. -]+)\]\s*$/i

interface SendContext {
  persona_id?: PersonaId
  level?: string
}

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

function isLanguageToolResult(data: WsEvent): data is Extract<WsEvent, { type: 'tool.result' }> {
  return data.type === 'tool.result' && (data.name === 'correct_text' || data.name === 'generate_quiz')
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
  let reconnecting = false
  let quizTtsMode = false

  function speakWithModel(event: Event) {
    const detail = (event as CustomEvent<ModelSpeechRequest>).detail
    const text = detail?.text?.trim()
    if (!text)
      return
    detail.onHandled?.()
    tts.stop()
    live2d.setEmotion('idle')
    void tts.enqueueText(text, 'idle', detail.language).finally(() => detail.onDone?.())
  }

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
      if (reconnecting) {
        reconnecting = false
        connect()
        return
      }
      if (!closedByUser) {
        retry += 1
        setTimeout(connect, Math.min(5000, 500 * retry))
      }
    }
    ws.onmessage = (e: MessageEvent) => {
      const data = JSON.parse(e.data as string) as WsEvent
      if (data.type === 'token') {
        const message = store.appendToken(data.content)
        // Quiz responses never auto-speak (questions play only via the QuizCard
        // ▶ button), so don't feed their text into the TTS queue.
        if (message && !quizTtsMode)
          tts.feedSnapshot(message.content)
      }
      else if (data.type === 'done') {
        const message = store.finalize()
        if (message?.content) {
          const parsed = parseVisualTags(message.content)
          message.content = parsed.content
          if (quizTtsMode) {
            // No auto-speech for quiz responses; keep only the visual emotion.
            live2d.setEmotion(parsed.emotion)
          }
          else {
            tts.flush(parsed.emotion)
            if (parsed.expression)
              tts.attachVisualCue({ expression: parsed.expression })
          }
        }
        else {
          live2d.setEmotion('idle')
        }
        quizTtsMode = false
      }
      else if (data.type === 'error') {
        store.setError(data.content)
        tts.stop()
      }
      else if (isLanguageToolResult(data)) {
        store.appendToolResult({
          name: data.name,
          payload: data.payload,
        } as LanguageToolResult)
        if (data.name === 'generate_quiz') {
          // Stop feeding new text into TTS from here on, but DON'T stop playback:
          // the lead-in sentence (e.g. "好的，我换一组新的填空题给你！") has already
          // been queued as a complete chunk and should finish. Calling stop() here
          // cut it off mid-sentence. Questions stream after this point and, with
          // quizTtsMode on, are never auto-spoken — only the QuizCard ▶ plays them.
          quizTtsMode = true
        }
      }
      else if (data.type === 'live2d.emotion') {
        // Defer the visual change to when the matching speech plays (synced via the
        // TTS queue) instead of applying it the moment the tag is parsed.
        tts.attachVisualCue({
          emotion: data.emotion,
          motion: data.motion,
          expression: data.expression,
          durationMs: data.durationMs,
          intensity: data.intensity,
        })
      }
    }
  }

  function reconnect() {
    retry = 0
    if (ws && ws.readyState !== WebSocket.CLOSED) {
      reconnecting = true
      ws.close()
      return
    }
    connect()
  }

  function send(text: string, context: SendContext = {}) {
    const t = text.trim()
    if (!t)
      return
    store.pushUser(t)
    tts.stop()
    quizTtsMode = false
    live2d.setThinking()
    store.startAssistant()
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ message: t, ...context }))
    else {
      store.setError('未连接到服务端')
      live2d.setEmotion('idle')
    }
  }

  onMounted(connect)
  onMounted(() => window.addEventListener(MODEL_SPEECH_EVENT, speakWithModel))
  watch(() => store.conversationId, () => {
    if (!closedByUser)
      reconnect()
  })
  onBeforeUnmount(() => {
    closedByUser = true
    window.removeEventListener(MODEL_SPEECH_EVENT, speakWithModel)
    ws?.close()
  })

  return { send }
}
