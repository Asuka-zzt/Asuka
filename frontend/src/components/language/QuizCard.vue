<script setup lang="ts">
import type { LanguageCode, QuizItem, QuizSet } from '@/types/language'

import { reactive, ref } from 'vue'

import { postTts } from '@/api/client'

const props = defineProps<{ quiz: QuizSet }>()
const answers = reactive<Record<number, string>>({})
const revealed = reactive<Record<number, boolean>>({})
const playingIndex = ref<number | null>(null)

async function speak(index: number, item: QuizItem, language: LanguageCode) {
  if (playingIndex.value !== null)
    return
  playingIndex.value = index
  try {
    const blob = await postTts(item.question, undefined, language)
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true })
    await audio.play()
  }
  finally {
    playingIndex.value = null
  }
}
</script>

<template>
  <section class="language-card quiz-card">
    <div class="card-head">
      <strong>{{ props.quiz.topic }} · {{ props.quiz.level }}</strong>
      <span>{{ props.quiz.items.length }} 题</span>
    </div>

    <article v-for="(item, index) in props.quiz.items" :key="`${item.question}-${index}`" class="quiz-item">
      <div class="question-row">
        <p>{{ index + 1 }}. {{ item.question }}</p>
        <button type="button" class="icon-button" title="朗读题干" @click="speak(index, item, props.quiz.language)">
          {{ playingIndex === index ? '...' : '▶' }}
        </button>
      </div>
      <div class="annotation">{{ item.annotation }}</div>

      <div v-if="item.type === 'mcq' && item.options" class="options">
        <button
          v-for="option in item.options"
          :key="option"
          type="button"
          :class="{ selected: answers[index] === option }"
          @click="answers[index] = option"
        >
          {{ option }}
        </button>
      </div>
      <input
        v-else
        v-model="answers[index]"
        class="answer-input"
        type="text"
        placeholder="输入答案"
      >

      <button type="button" class="reveal" @click="revealed[index] = !revealed[index]">
        {{ revealed[index] ? '收起解析' : '查看解析' }}
      </button>
      <div v-if="revealed[index]" class="explanation">
        <strong>答案：{{ item.answer }}</strong>
        <p>{{ item.explanation_zh }}</p>
      </div>
    </article>
  </section>
</template>

<style scoped>
.language-card {
  margin-top: 0.6rem;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
}

.card-head,
.question-row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: flex-start;
}

.card-head span,
.annotation {
  font-size: 0.78rem;
  opacity: 0.7;
}

.quiz-item {
  padding-top: 0.75rem;
  margin-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.question-row p {
  margin: 0;
  white-space: pre-wrap;
}

.icon-button {
  flex: 0 0 auto;
  width: 1.8rem;
  height: 1.8rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
}

.options {
  display: grid;
  gap: 0.35rem;
  margin-top: 0.55rem;
}

.options button,
.answer-input {
  width: 100%;
  padding: 0.45rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 0.45rem;
  background: var(--surface-2);
  color: var(--text);
  text-align: left;
}

.options button.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.answer-input {
  margin-top: 0.55rem;
}

.reveal {
  margin-top: 0.55rem;
  color: var(--primary);
  font-size: 0.82rem;
}

.explanation {
  margin-top: 0.45rem;
  padding: 0.55rem;
  border-radius: 0.45rem;
  background: var(--surface-2);
}

.explanation p {
  margin: 0.25rem 0 0;
}
</style>
