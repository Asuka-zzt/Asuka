import type { EmotionType } from '@/types/live2d'

import { onBeforeUnmount } from 'vue'

import { postTts } from '@/api/client'
import { useLive2DStore } from '@/stores/live2d'

interface AudioWindow extends Window {
  webkitAudioContext?: typeof AudioContext
}

function createAudioContext(): AudioContext {
  const AudioContextCtor = window.AudioContext ?? (window as AudioWindow).webkitAudioContext
  if (!AudioContextCtor)
    throw new Error('AudioContext is not supported')
  return new AudioContextCtor()
}

export function useTtsAudio() {
  const live2d = useLive2DStore()
  let audio: HTMLAudioElement | undefined
  let objectUrl: string | undefined
  let audioContext: AudioContext | undefined
  let raf = 0
  let playToken = 0

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

  async function playText(text: string, emotion: EmotionType = 'idle'): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed)
      return

    const token = ++playToken
    releaseAudio()
    live2d.setEmotion(emotion)

    try {
      const blob = await postTts(trimmed)
      if (token !== playToken)
        return

      objectUrl = URL.createObjectURL(blob)
      audio = new Audio(objectUrl)
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
        if (token === playToken) {
          releaseAudio()
          live2d.setEmotion('idle')
        }
      }, { once: true })

      audio.addEventListener('error', () => {
        if (token === playToken) {
          releaseAudio()
          live2d.setEmotion('idle')
        }
      }, { once: true })

      await audio.play()
      if (token !== playToken)
        return

      live2d.setSpeaking(true)
      analyse(analyser, token)
    }
    catch (err) {
      if (token === playToken) {
        console.warn('[tts] audio playback failed:', err)
        releaseAudio()
        live2d.setEmotion('idle')
      }
    }
  }

  function stop(): void {
    playToken += 1
    releaseAudio()
    live2d.setEmotion('idle')
  }

  onBeforeUnmount(() => {
    stop()
    void audioContext?.close()
    audioContext = undefined
  })

  return { playText, stop }
}
