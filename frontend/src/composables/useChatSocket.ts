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
const QUESTION_START_RE = /^\s*(?:#{1,6}\s*)?(?:(?:\d+|[1-9]️⃣)[.)、]?\s*|(?:\*\*)?(?:Question|题目)\s*\d+)/i
const CLOSING_RE = /^\s*(?:你|如果|需要|想要|答完|完成|告诉我|可以|再来)/

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

function extractQuizSpeechSegments(content: string): { intro: string, closing: string } {
  const lines = content.split('\n')
  const firstQuestion = lines.findIndex(line => QUESTION_START_RE.test(line.trim()))
  if (firstQuestion === -1)
    return { intro: content.trim(), closing: '' }

  const intro = lines.slice(0, firstQuestion).join('\n').trim()
  const closingStart = lines.findIndex((line, index) =>
    index > firstQuestion && CLOSING_RE.test(line.trim()),
  )
  const closing = closingStart === -1 ? '' : lines.slice(closingStart).join('\n').trim()
  return { intro, closing }
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
  let hadPreQuizSpeech = false

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
        if (message && !quizTtsMode) {
          tts.feedSnapshot(message.content)
          if (data.content.trim())
            hadPreQuizSpeech = true
        }
      }
      else if (data.type === 'done') {
        const message = store.finalize()
        if (message?.content) {
          const parsed = parseVisualTags(message.content)
          message.content = parsed.content
          if (quizTtsMode) {
            tts.flush(parsed.emotion)
            const segments = extractQuizSpeechSegments(parsed.content)
            if (!hadPreQuizSpeech && segments.intro)
              tts.enqueueText(segments.intro, undefined)
            if (segments.closing)
              tts.enqueueText(segments.closing, undefined)
          }
          else {
            tts.flush(parsed.emotion)
          }
          if (!quizTtsMode && parsed.expression)
            tts.attachVisualCue({ expression: parsed.expression })
        }
        else {
          live2d.setEmotion('idle')
        }
        quizTtsMode = false
        hadPreQuizSpeech = false
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
    hadPreQuizSpeech = false
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
