import type { EmotionType } from '@/types/live2d'
import type { LanguageToolResult } from '@/types/language'
import type { RealtimeEvent, VoiceState } from '@/types/realtime'

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { closeRealtimeSession, createRealtimeSession, postRealtimeOffer } from '@/api/client'
import { useChatStore } from '@/stores/chat'
import { useLive2DStore } from '@/stores/live2d'

interface AudioWindow extends Window {
  webkitAudioContext?: typeof AudioContext
}

const COMPLETE_ICE_TIMEOUT_MS = 1800
const DEFAULT_EXPRESSION_DURATION_MS = 1800

function uid(): string {
  return Math.random().toString(36).slice(2, 10)
}

function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === 'complete')
    return Promise.resolve()

  return new Promise((resolve) => {
    const timeout = window.setTimeout(done, COMPLETE_ICE_TIMEOUT_MS)
    function done() {
      window.clearTimeout(timeout)
      pc.removeEventListener('icegatheringstatechange', onChange)
      resolve()
    }
    function onChange() {
      if (pc.iceGatheringState === 'complete')
        done()
    }
    pc.addEventListener('icegatheringstatechange', onChange)
  })
}

function eventEnvelope(type: string, conversationId: string, sessionId: string, payload: Record<string, unknown> = {}) {
  return JSON.stringify({
    type,
    id: uid(),
    conversationId,
    sessionId,
    createdAt: Date.now(),
    payload,
  })
}

function parseEmotion(value: unknown): EmotionType | undefined {
  if (value === 'idle' || value === 'think' || value === 'happy' || value === 'sad')
    return value
  return undefined
}

function parseLanguageToolResult(payload: Record<string, unknown>): LanguageToolResult | undefined {
  if (payload.name === 'correct_text')
    return { name: 'correct_text', payload: payload.payload as LanguageToolResult['payload'] } as LanguageToolResult
  if (payload.name === 'generate_quiz')
    return { name: 'generate_quiz', payload: payload.payload as LanguageToolResult['payload'] } as LanguageToolResult
  return undefined
}

export function useRealtimeVoice() {
  const store = useChatStore()
  const live2d = useLive2DStore()

  const voiceState = ref<VoiceState>('idle')
  const interimTranscript = ref('')
  const voiceSupported = ref(false)

  let pc: RTCPeerConnection | undefined
  let dc: RTCDataChannel | undefined
  let sessionId: string | undefined
  let localStream: MediaStream | undefined
  let localAudioSender: RTCRtpSender | undefined
  let remoteAudio: HTMLAudioElement | undefined
  let audioContext: AudioContext | undefined
  let remoteAnalyser: AnalyserNode | undefined
  let remoteAnalysisRaf = 0
  let closedByUser = false
  let connectingPromise: Promise<void> | undefined
  let pendingClientTranscript = ''
  let audioUnlockHandler: (() => void) | undefined

  function createAudioContext(): AudioContext {
    const AudioContextCtor = window.AudioContext ?? (window as AudioWindow).webkitAudioContext
    if (!AudioContextCtor)
      throw new Error('AudioContext is not supported')
    return new AudioContextCtor()
  }

  // Browsers block audio playback (AudioContext + media element) until a user
  // gesture. The session auto-connects on mount with no gesture, so remote
  // audio must be unlocked from a real interaction or it stays silent.
  async function unlockAudio(): Promise<void> {
    try {
      audioContext ??= createAudioContext()
      if (audioContext.state === 'suspended')
        await audioContext.resume()
    }
    catch {
      // Not in a gesture yet; the next interaction will retry.
    }
    if (remoteAudio)
      void remoteAudio.play().catch(() => undefined)
  }

  function sendDataChannelEvent(type: string, payload: Record<string, unknown> = {}) {
    if (!dc || dc.readyState !== 'open' || !sessionId) {
      store.setError('实时语音链路未连接')
      return
    }
    dc.send(eventEnvelope(type, store.conversationId, sessionId, payload))
  }

  function stopRemoteAnalysis() {
    if (remoteAnalysisRaf) {
      cancelAnimationFrame(remoteAnalysisRaf)
      remoteAnalysisRaf = 0
    }
    remoteAnalyser = undefined
    live2d.setSpeaking(false)
  }

  function analyseRemoteAudio(analyser: AnalyserNode) {
    const samples = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(samples)
      let squareSum = 0
      for (const sample of samples) {
        const centered = (sample - 128) / 128
        squareSum += centered * centered
      }

      const rms = Math.sqrt(squareSum / samples.length)
      live2d.setMouthOpen(Math.min(1, rms * 3.6))
      if (rms > 0.012)
        live2d.setSpeaking(true)
      remoteAnalysisRaf = requestAnimationFrame(tick)
    }
    tick()
  }

  async function attachRemoteAudio(stream: MediaStream) {
    remoteAudio ??= new Audio()
    remoteAudio.autoplay = true
    remoteAudio.srcObject = stream
    void remoteAudio.play().catch(() => undefined)

    audioContext ??= createAudioContext()
    if (audioContext.state === 'suspended')
      await audioContext.resume().catch(() => undefined)
    stopRemoteAnalysis()
    const source = audioContext.createMediaStreamSource(stream)
    remoteAnalyser = audioContext.createAnalyser()
    remoteAnalyser.fftSize = 512
    remoteAnalyser.smoothingTimeConstant = 0.55
    source.connect(remoteAnalyser)
    analyseRemoteAudio(remoteAnalyser)
  }

  function setLocalMicEnabled(enabled: boolean) {
    localStream?.getAudioTracks().forEach((track) => {
      track.enabled = enabled
    })
  }

  async function acquireLocalAudio(enabled: boolean): Promise<void> {
    localStream?.getTracks().forEach(track => track.stop())
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    setLocalMicEnabled(enabled)
    const track = localStream.getAudioTracks()[0]
    if (!pc || !track)
      return
    if (localAudioSender)
      await localAudioSender.replaceTrack(track)
    else
      localAudioSender = pc.addTrack(track, localStream)
  }

  function applyVisualCue(payload: Record<string, unknown>) {
    const emotion = parseEmotion(payload.emotion)
    const motion = typeof payload.motion === 'string' ? payload.motion : undefined
    if (emotion)
      live2d.setEmotion(emotion, motion ? { group: motion } : undefined)
    if (typeof payload.expression === 'string') {
      live2d.setExpression({
        name: payload.expression,
        durationMs: typeof payload.durationMs === 'number'
          ? payload.durationMs
          : DEFAULT_EXPRESSION_DURATION_MS,
        intensity: typeof payload.intensity === 'number' ? payload.intensity : undefined,
      })
    }
  }

  function handleRealtimeEvent(event: RealtimeEvent<Record<string, unknown>>) {
    if (event.type === 'session.ready') {
      store.connected = true
      if (voiceState.value === 'connecting')
        voiceState.value = 'idle'
      return
    }

    if (event.type === 'input.speech_start') {
      voiceState.value = 'listening'
      interimTranscript.value = ''
      return
    }

    if (event.type === 'input.speech_end') {
      voiceState.value = 'transcribing'
      return
    }

    if (event.type === 'input.transcript.final') {
      const text = String(event.payload.text ?? '').trim()
      if (text && text !== pendingClientTranscript) {
        store.pushUser(text)
        store.startAssistant()
      }
      pendingClientTranscript = ''
      interimTranscript.value = ''
      return
    }

    if (event.type === 'input.transcript.partial') {
      interimTranscript.value = String(event.payload.text ?? '')
      return
    }

    if (event.type === 'chat.token') {
      store.appendToken(String(event.payload.content ?? ''))
      return
    }

    if (event.type === 'tool.result') {
      const result = parseLanguageToolResult(event.payload)
      if (result)
        store.appendToolResult(result)
      return
    }

    if (event.type === 'live2d.emotion') {
      applyVisualCue(event.payload)
      return
    }

    if (event.type === 'voice.speech_start') {
      voiceState.value = 'speaking'
      live2d.setSpeaking(true)
      return
    }

    if (event.type === 'voice.speech_end') {
      live2d.setSpeaking(false)
      return
    }

    if (event.type === 'done') {
      const message = store.finalize()
      if (message?.content)
        live2d.setEmotion('idle')
      else
        live2d.setEmotion('idle')
      if (voiceState.value !== 'speaking')
        voiceState.value = 'idle'
      return
    }

    if (event.type === 'error') {
      store.setError(String(event.payload.message ?? '实时语音链路错误'))
      live2d.setSpeaking(false)
      voiceState.value = 'error'
    }
  }

  async function connect(): Promise<void> {
    if (dc?.readyState === 'open')
      return
    if (connectingPromise)
      return connectingPromise

    voiceState.value = 'connecting'
    connectingPromise = (async () => {
      const session = await createRealtimeSession(store.conversationId)
      sessionId = session.session_id

      pc = new RTCPeerConnection()
      dc = pc.createDataChannel('asuka-events')
      dc.onopen = () => {
        store.connected = true
        voiceState.value = 'idle'
      }
      dc.onclose = () => {
        store.connected = false
      }
      dc.onerror = () => {
        store.connected = false
        voiceState.value = 'error'
      }
      dc.onmessage = (message: MessageEvent<string>) => {
        handleRealtimeEvent(JSON.parse(message.data) as RealtimeEvent<Record<string, unknown>>)
      }

      pc.ontrack = (event) => {
        const stream = event.streams[0] ?? new MediaStream([event.track])
        void attachRemoteAudio(stream)
      }
      pc.onconnectionstatechange = () => {
        if (!pc)
          return
        if (pc.connectionState === 'connected')
          store.connected = true
        if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected' || pc.connectionState === 'closed')
          store.connected = false
      }

      localAudioSender = pc.addTransceiver('audio', { direction: 'sendrecv' }).sender

      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      await waitForIceGatheringComplete(pc)
      if (!pc.localDescription)
        throw new Error('WebRTC localDescription is empty')

      const answer = await postRealtimeOffer(sessionId, {
        sdp: pc.localDescription.sdp,
        type: 'offer',
      })
      await pc.setRemoteDescription(answer)
    })().catch((error) => {
      store.connected = false
      voiceState.value = 'error'
      throw error
    }).finally(() => {
      connectingPromise = undefined
    })

    return connectingPromise
  }

  function send(text: string) {
    const content = text.trim()
    if (!content)
      return
    void unlockAudio()
    void connect().then(() => {
      if (!dc || dc.readyState !== 'open' || !sessionId) {
        store.setError('实时语音链路未连接')
        return
      }
      pendingClientTranscript = content
      store.pushUser(content)
      store.startAssistant()
      live2d.setThinking()
      sendDataChannelEvent('text.send', { content })
    }).catch((error: unknown) => {
      store.setError(error instanceof Error ? error.message : '实时语音链路连接失败')
    })
  }

  function startVoiceInput() {
    void unlockAudio()
    void connect().then(() => {
      if (!localStream)
        return acquireLocalAudio(true)
      setLocalMicEnabled(true)
      return undefined
    }).then(() => {
      voiceSupported.value = true
      interimTranscript.value = ''
      voiceState.value = 'listening'
    }).catch((error: unknown) => {
      store.setError(error instanceof Error ? error.message : '无法启动语音输入')
      voiceSupported.value = false
      voiceState.value = 'error'
    })
  }

  function stopVoiceInput() {
    setLocalMicEnabled(false)
    voiceState.value = 'transcribing'
    sendDataChannelEvent('input.audio.commit')
  }

  async function disconnect(): Promise<void> {
    closedByUser = true
    stopRemoteAnalysis()
    localStream?.getTracks().forEach(track => track.stop())
    localStream = undefined
    localAudioSender = undefined
    dc?.close()
    dc = undefined
    pc?.close()
    pc = undefined
    store.connected = false
    if (sessionId)
      await closeRealtimeSession(sessionId).catch(() => undefined)
    sessionId = undefined
  }

  onMounted(() => {
    voiceSupported.value = Boolean(
      'mediaDevices' in navigator
      && 'RTCPeerConnection' in window,
    )
    // Unlock audio on the first user interaction anywhere on the page, since the
    // session connects before any gesture and would otherwise stay muted.
    audioUnlockHandler = () => {
      void unlockAudio()
    }
    window.addEventListener('pointerdown', audioUnlockHandler)
    window.addEventListener('keydown', audioUnlockHandler)
    void connect().catch(() => undefined)
  })

  watch(() => store.conversationId, () => {
    if (!closedByUser) {
      void disconnect().finally(() => {
        closedByUser = false
        void connect().catch(() => undefined)
      })
    }
  })

  onBeforeUnmount(() => {
    if (audioUnlockHandler) {
      window.removeEventListener('pointerdown', audioUnlockHandler)
      window.removeEventListener('keydown', audioUnlockHandler)
      audioUnlockHandler = undefined
    }
    void disconnect()
  })

  return {
    send,
    connect,
    disconnect,
    startVoiceInput,
    stopVoiceInput,
    voiceState,
    interimTranscript,
    voiceSupported,
  }
}
