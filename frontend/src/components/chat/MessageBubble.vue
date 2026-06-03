<script setup lang="ts">
import type { Message } from '@/types/chat'

import CorrectionCard from '@/components/language/CorrectionCard.vue'
import QuizCard from '@/components/language/QuizCard.vue'
import MarkdownText from './MarkdownText.vue'

defineProps<{ message: Message }>()
</script>

<template>
  <div class="row" :class="message.role === 'user' ? 'right' : 'left'">
    <div class="bubble" :class="message.role">
      <MarkdownText :content="message.content" />
      <span v-if="message.streaming" class="cursor">▍</span>
      <template v-if="message.toolResults?.length">
        <template v-for="(result, index) in message.toolResults" :key="`${result.name}-${index}`">
          <CorrectionCard v-if="result.name === 'correct_text'" :result="result.payload" />
          <QuizCard v-else-if="result.name === 'generate_quiz'" :quiz="result.payload" />
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
}

.row.right {
  justify-content: flex-end;
}

.row.left {
  justify-content: flex-start;
}

.bubble {
  max-width: min(80%, 42rem);
  padding: 0.6rem 0.8rem;
  border-radius: 0.9rem;
  font-size: 0.9rem;
  line-height: 1.55;
}

.bubble.user {
  background: var(--primary);
  color: var(--on-primary);
  border-bottom-right-radius: 0.2rem;
}

.bubble.assistant {
  background: var(--surface-2);
  color: var(--text);
  border-bottom-left-radius: 0.2rem;
}

.cursor {
  animation: blink 1s steps(2) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
