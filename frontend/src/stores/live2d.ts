import type { EmotionType, Live2DExpressionCommand, Live2DMotionCommand } from '@/types/live2d'

import { defineStore } from 'pinia'
import { ref } from 'vue'

const DEFAULT_MOTION_GROUPS: Record<EmotionType, string> = {
  idle: 'Idle',
  think: 'Think',
  happy: 'Happy',
  sad: 'Sad',
}

function envMotion(key: string, fallback: string): string {
  if (Object.prototype.hasOwnProperty.call(import.meta.env, key))
    return String(import.meta.env[key])
  return fallback
}

export function motionGroupForEmotion(emotion: EmotionType): string {
  const envKey = `VITE_LIVE2D_MOTION_${emotion.toUpperCase()}`
  return envMotion(envKey, DEFAULT_MOTION_GROUPS[emotion])
}

export const useLive2DStore = defineStore('live2d', () => {
  const emotion = ref<EmotionType>('idle')
  const motionCommand = ref<Live2DMotionCommand>({
    group: motionGroupForEmotion('idle'),
  })
  const expressionCommand = ref<Live2DExpressionCommand>()
  const speaking = ref(false)
  const mouthOpen = ref(0)

  function setEmotion(nextEmotion: EmotionType, motion?: Live2DMotionCommand): void {
    emotion.value = nextEmotion
    motionCommand.value = motion ?? { group: motionGroupForEmotion(nextEmotion) }
  }

  function setThinking(): void {
    setEmotion('think')
  }

  function setSpeaking(value: boolean): void {
    speaking.value = value
    if (!value)
      mouthOpen.value = 0
  }

  function setMouthOpen(value: number): void {
    mouthOpen.value = Math.min(1, Math.max(0, value))
  }

  function setExpression(command: Live2DExpressionCommand | undefined): void {
    expressionCommand.value = command
  }

  function clearInstruction(): void {
    setExpression(undefined)
    setSpeaking(false)
    setEmotion('idle')
  }

  return {
    emotion,
    motionCommand,
    expressionCommand,
    speaking,
    mouthOpen,
    setEmotion,
    setThinking,
    setSpeaking,
    setMouthOpen,
    setExpression,
    clearInstruction,
  }
})
