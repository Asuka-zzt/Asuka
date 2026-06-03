import type { LanguageCode } from '@/types/language'

export const MODEL_SPEECH_EVENT = 'asuka:model-speech'

export interface ModelSpeechRequest {
  text: string
  language?: LanguageCode
  onHandled?: () => void
  onDone?: () => void
}

export function requestModelSpeech(text: string, language?: LanguageCode): Promise<void> {
  return new Promise((resolve) => {
    let handled = false
    window.dispatchEvent(
      new CustomEvent<ModelSpeechRequest>(MODEL_SPEECH_EVENT, {
        detail: {
          text,
          language,
          onHandled: () => {
            handled = true
          },
          onDone: resolve,
        },
      }),
    )
    if (!handled)
      resolve()
  })
}
