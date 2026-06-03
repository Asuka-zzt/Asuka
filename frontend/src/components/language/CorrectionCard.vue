<script setup lang="ts">
import type { CorrectionResult, LanguageCode } from '@/types/language'

import { ref } from 'vue'

import { requestModelSpeech } from '@/composables/modelSpeech'

const props = defineProps<{ result: CorrectionResult }>()
const playing = ref(false)
const error = ref('')

async function speak(text: string, language: LanguageCode) {
  if (!text.trim() || playing.value)
    return
  playing.value = true
  error.value = ''
  try {
    await requestModelSpeech(text, language)
  }
  catch {
    error.value = '朗读失败'
  }
  finally {
    playing.value = false
  }
}
</script>

<template>
  <section class="language-card">
    <div class="card-head">
      <strong>纠错</strong>
      <button type="button" class="icon-button" title="朗读地道改写" @click="speak(props.result.natural_rewrite, props.result.language)">
        {{ playing ? '...' : '▶' }}
      </button>
    </div>

    <div v-if="props.result.items.length" class="corrections">
      <div v-for="item in props.result.items" :key="`${item.error_type}-${item.original}`" class="correction">
        <div class="error-type">{{ item.error_type }}</div>
        <div class="pair">
          <span class="original">{{ item.original }}</span>
          <span class="arrow">-&gt;</span>
          <span class="corrected">{{ item.corrected }}</span>
        </div>
        <p>{{ item.explanation_zh }}</p>
      </div>
    </div>
    <p v-else class="muted">这句整体没有明显错误。</p>

    <div class="rewrite">
      <span>地道说法</span>
      <p>{{ props.result.natural_rewrite }}</p>
    </div>
    <div class="annotation">{{ props.result.annotation }}</div>
    <div class="encouragement">{{ props.result.encouragement_zh }}</div>
    <div v-if="error" class="audio-error">{{ error }}</div>
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

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: center;
}

.icon-button {
  width: 1.8rem;
  height: 1.8rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
}

.corrections {
  display: grid;
  gap: 0.55rem;
  margin-top: 0.6rem;
}

.correction {
  padding-top: 0.55rem;
  border-top: 1px solid var(--border);
}

.error-type {
  font-size: 0.78rem;
  color: var(--primary);
  font-weight: 600;
}

.pair {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.25rem 0;
}

.original {
  text-decoration: line-through;
  opacity: 0.65;
}

.corrected {
  font-weight: 600;
}

.rewrite {
  margin-top: 0.7rem;
}

.rewrite span,
.annotation,
.muted,
.audio-error {
  font-size: 0.78rem;
  opacity: 0.7;
}

.rewrite p,
.correction p {
  margin: 0.25rem 0 0;
  white-space: pre-wrap;
}

.encouragement {
  margin-top: 0.5rem;
}

.audio-error {
  color: var(--danger);
}
</style>
