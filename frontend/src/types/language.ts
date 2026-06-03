export type LanguageCode = 'english' | 'japanese'
export type PersonaId = 'english_teacher' | 'japanese_teacher'
export type QuizType = 'mcq' | 'cloze' | 'translation'

export interface CorrectionItem {
  error_type: string
  original: string
  corrected: string
  explanation_zh: string
}

export interface CorrectionResult {
  has_error: boolean
  language: LanguageCode
  items: CorrectionItem[]
  natural_rewrite: string
  annotation: string
  encouragement_zh: string
}

export interface QuizItem {
  type: QuizType
  question: string
  options: string[] | null
  answer: string
  explanation_zh: string
  annotation: string
}

export interface QuizSet {
  language: LanguageCode
  level: string
  topic: string
  items: QuizItem[]
}

export type LanguageToolResult =
  | { name: 'correct_text', payload: CorrectionResult }
  | { name: 'generate_quiz', payload: QuizSet }
