<script setup lang="ts">
import type { Message } from '@/types/chat'

defineProps<{ message: Message }>()
</script>

<template>
  <div class="row" :class="message.role === 'user' ? 'right' : 'left'">
    <div class="bubble" :class="message.role">
      <span class="text">{{ message.content }}</span>
      <span v-if="message.streaming" class="cursor">▍</span>
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
  max-width: 80%;
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

.text {
  white-space: pre-wrap;
  word-break: break-word;
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
