import type { EmotionType } from '@/types/live2d'

import { onBeforeUnmount } from 'vue'

import { postTts } from '@/api/client'
import { useLive2DStore } from '@/stores/live2d'

interface AudioWindow extends Window {
  webkitAudioContext?: typeof AudioContext
}

interface QueuedSpeech {
  text: string
  emotion?: EmotionType
}

const CHUNK_BOUNDARY_RE = /[。！？!?；;]\s*/
const EMOTION_TAG_RE = /\[emotion:(idle|think|happy|sad)\]\s*$/i
const MIN_STREAM_CHARS = 48

function createAudioContext(): AudioContext {
  const AudioContextCtor = window.AudioContext ?? (window as AudioWindow).webkitAudioContext
  if (!AudioContextCtor)
    throw new Error('AudioContext is not supported')
  return new AudioContextCtor()
}

function waitForEvent(target: EventTarget, event: string): Promise<void> {
  return new Promise((resolve) => {
    target.addEventListener(event, () => resolve(), { once: true })
  })
}

function stripTrailingEmotionTag(text: string): string {
  return text.replace(EMOTION_TAG_RE, '').trimEnd()
}

export function useTtsAudio() {
  const live2d = useLive2DStore()
  let audio: HTMLAudioElement | undefined
  let objectUrl: string | undefined
  let audioContext: AudioContext | undefined
  let raf = 0
  let playToken = 0
  let pendingText = ''
  let playing = false
  const queue: QueuedSpeech[] = []

  function releaseAudio(): void {
    if (raf) {
      cancelAnimationFrame(raf)
      raf = 0
    }
    if (audio) {
      audio.pause()
      audio.src = ''
      audio = undefined
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl)
      objectUrl = undefined
    }
    live2d.setSpeaking(false)
  }

  function analyse(analyser: AnalyserNode, token: number): void {
    const samples = new Uint8Array(analyser.fftSize)
    const tick = () => {
      if (token !== playToken)
        return

      analyser.getByteTimeDomainData(samples)
      let squareSum = 0
      for (const sample of samples) {
        const centered = (sample - 128) / 128
        squareSum += centered * centered
      }

      const rms = Math.sqrt(squareSum / samples.length)
      live2d.setMouthOpen(Math.min(1, rms * 3.4))
      raf = requestAnimationFrame(tick)
    }
    tick()
  }

  async function prepareAudioElement(token: number): Promise<AnalyserNode> {
    audio = new Audio()
    audio.crossOrigin = 'anonymous'
    audioContext ??= createAudioContext()
    if (audioContext.state === 'suspended')
      await audioContext.resume()

    const source = audioContext.createMediaElementSource(audio)
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 512
    analyser.smoothingTimeConstant = 0.55
    source.connect(analyser)
    analyser.connect(audioContext.destination)

    audio.addEventListener('ended', () => {
      if (token === playToken)
        releaseAudio()
    }, { once: true })
    audio.addEventListener('error', () => {
      if (token === playToken)
        releaseAudio()
    }, { once: true })

    return analyser
  }

  async function playWithBlob(text: string, token: number): Promise<void> {
    const blob = await postTts(text)
    if (token !== playToken)
      return

    objectUrl = URL.createObjectURL(blob)
    if (!audio)
      return

    audio.src = objectUrl
    await audio.play()
  }

  async function playQueuedSegment(segment: QueuedSpeech, token: number): Promise<void> {
    releaseAudio()
    if (segment.emotion)
      live2d.setEmotion(segment.emotion)

    const analyser = await prepareAudioElement(token)
    if (token !== playToken)
      return

    live2d.setSpeaking(true)
    analyse(analyser, token)

    await playWithBlob(segment.text, token)

    if (!audio)
      return

    if (!audio.ended)
      await waitForEvent(audio, 'ended')
  }

  async function drainQueue(token: number): Promise<void> {
    if (playing)
      return

    playing = true
    try {
      while (token === playToken && queue.length) {
        const segment = queue.shift()
        if (!segment)
          continue

        try {
          await playQueuedSegment(segment, token)
        }
        catch (err) {
          console.warn('[tts] streaming playback failed:', err)
          releaseAudio()
        }
      }
    }
    finally {
      playing = false
      if (token === playToken) {
        releaseAudio()
        live2d.setEmotion('idle')
      }
    }
  }

  function enqueueText(text: string, emotion?: EmotionType): void {
    const clean = stripTrailingEmotionTag(text).trim()
    if (!clean)
      return

    queue.push({ text: clean, emotion })
    void drainQueue(playToken)
  }

  function takeNextChunk(flush = false): string | undefined {
    pendingText = stripTrailingEmotionTag(pendingText)
    const trimmedStart = pendingText.trimStart()
    pendingText = trimmedStart

    const boundary = CHUNK_BOUNDARY_RE.exec(pendingText)
    if (boundary?.index !== undefined) {
      const end = boundary.index + boundary[0].length
      const chunk = pendingText.slice(0, end)
      pendingText = pendingText.slice(end)
      return chunk
    }

    if (pendingText.length >= MIN_STREAM_CHARS) {
      const chunk = pendingText.slice(0, MIN_STREAM_CHARS)
      pendingText = pendingText.slice(MIN_STREAM_CHARS)
      return chunk
    }

    if (flush && pendingText.trim()) {
      const chunk = pendingText
      pendingText = ''
      return chunk
    }

    return undefined
  }

  function feedToken(tokenText: string): void {
    pendingText += tokenText
    let chunk = takeNextChunk()
    while (chunk) {
      enqueueText(chunk)
      chunk = takeNextChunk()
    }
  }

  function flush(emotion?: EmotionType): void {
    let chunk = takeNextChunk(true)
    while (chunk) {
      enqueueText(chunk, emotion)
      chunk = takeNextChunk(true)
      emotion = undefined
    }
    if (emotion)
      live2d.setEmotion(emotion)
  }

  function stop(): void {
    playToken += 1
    queue.length = 0
    pendingText = ''
    playing = false
    releaseAudio()
    live2d.setEmotion('idle')
  }

  onBeforeUnmount(() => {
    stop()
    void audioContext?.close()
    audioContext = undefined
  })

  return { feedToken, flush, enqueueText, stop }
}
