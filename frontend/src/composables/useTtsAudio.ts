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
  retries: number
  blobPromise: Promise<TtsBlobResult>
}

type TtsBlobResult =
  | { ok: true, blob: Blob }
  | { ok: false, error: unknown }

const CHUNK_BOUNDARY_RE = /[。！？!?；;]\s*/
const EMOTION_TAG_RE = /\[emotion:(idle|think|happy|sad)\]\s*$/i
const EMOJI_RE = /[\p{Extended_Pictographic}\uFE0F\u200D\u20E3]/gu
const URL_RE = /https?:\/\/\S+/gi
const FIRST_CHUNK_CHARS = 18
const NEXT_CHUNK_CHARS = 42

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

function cleanForSpeech(text: string): string {
  return stripTrailingEmotionTag(text)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(URL_RE, ' ')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-+*]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/[*_~^|#[\]{}<>]/g, '')
    .replace(/[，,、]\s*/g, '，')
    .replace(EMOJI_RE, '')
    .replace(/\s+/g, ' ')
    .trim()
}

async function preloadTts(text: string): Promise<TtsBlobResult> {
  try {
    return { ok: true, blob: await postTts(text) }
  }
  catch (error) {
    return { ok: false, error }
  }
}

export function useTtsAudio() {
  const live2d = useLive2DStore()
  let audio: HTMLAudioElement | undefined
  let analyser: AnalyserNode | undefined
  let objectUrl: string | undefined
  let audioContext: AudioContext | undefined
  let raf = 0
  let playToken = 0
  let pendingText = ''
  let lastSnapshot = ''
  let chunksQueued = 0
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

  async function ensureAudioPipeline(): Promise<AnalyserNode> {
    if (audio && analyser)
      return analyser

    audio = new Audio()
    audio.preload = 'auto'
    audioContext ??= createAudioContext()
    if (audioContext.state === 'suspended')
      await audioContext.resume()

    const source = audioContext.createMediaElementSource(audio)
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 512
    analyser.smoothingTimeConstant = 0.55
    source.connect(analyser)
    analyser.connect(audioContext.destination)

    return analyser
  }

  function clearSegmentUrl(): void {
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl)
      objectUrl = undefined
    }
  }

  async function playQueuedSegment(segment: QueuedSpeech, token: number): Promise<boolean> {
    clearSegmentUrl()
    if (segment.emotion)
      live2d.setEmotion(segment.emotion)

    const activeAnalyser = await ensureAudioPipeline()
    if (token !== playToken)
      return true

    const result = await segment.blobPromise
    if (!result.ok)
      throw result.error
    if (token !== playToken)
      return true
    if (!audio)
      return false

    objectUrl = URL.createObjectURL(result.blob)
    audio.src = objectUrl
    live2d.setSpeaking(true)
    analyse(activeAnalyser, token)
    await audio.play()
    await Promise.race([
      waitForEvent(audio, 'ended'),
      waitForEvent(audio, 'error').then(() => {
        throw new Error('audio playback failed')
      }),
    ])

    clearSegmentUrl()
    return true
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
          const ok = await playQueuedSegment(segment, token)
          if (!ok && segment.retries < 1)
            queue.unshift(retrySegment(segment))
        }
        catch (err) {
          console.warn('[tts] streaming playback failed:', err)
          clearSegmentUrl()
          if (segment.retries < 1)
            queue.unshift(retrySegment(segment))
        }
      }
    }
    finally {
      playing = false
      if (token === playToken && queue.length) {
        void drainQueue(token)
        return
      }
      if (token === playToken) {
        releaseAudio()
        live2d.setEmotion('idle')
      }
    }
  }

  function enqueueText(text: string, emotion?: EmotionType): void {
    const clean = cleanForSpeech(text)
    if (!clean)
      return

    queue.push({
      text: clean,
      emotion,
      retries: 0,
      blobPromise: preloadTts(clean),
    })
    chunksQueued += 1
    void drainQueue(playToken)
  }

  function retrySegment(segment: QueuedSpeech): QueuedSpeech {
    return {
      ...segment,
      retries: segment.retries + 1,
      blobPromise: preloadTts(segment.text),
    }
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

    const minChars = chunksQueued === 0 ? FIRST_CHUNK_CHARS : NEXT_CHUNK_CHARS
    if (pendingText.length >= minChars) {
      const chunk = pendingText.slice(0, minChars)
      pendingText = pendingText.slice(minChars)
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

  function feedSnapshot(content: string): void {
    if (content.startsWith(lastSnapshot)) {
      feedToken(content.slice(lastSnapshot.length))
      lastSnapshot = content
      return
    }

    const commonLength = sharedPrefixLength(lastSnapshot, content)
    feedToken(content.slice(commonLength))
    lastSnapshot = content
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
    lastSnapshot = ''
    chunksQueued = 0
    playing = false
    releaseAudio()
    audio = undefined
    analyser = undefined
    live2d.setEmotion('idle')
  }

  onBeforeUnmount(() => {
    stop()
    void audioContext?.close()
    audioContext = undefined
  })

  return { feedToken, feedSnapshot, flush, enqueueText, stop }
}

function sharedPrefixLength(a: string, b: string): number {
  const max = Math.min(a.length, b.length)
  let index = 0
  while (index < max && a[index] === b[index])
    index += 1
  return index
}
