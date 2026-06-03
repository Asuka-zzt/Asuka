<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ sending: boolean, connected: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()

const text = ref('')

function submit() {
  const t = text.value.trim()
  if (!t || props.sending)
    return
  emit('send', t)
  text.value = ''
}
</script>

<template>
  <div class="input-bar">
    <div class="row">
      <textarea
        v-model="text"
        rows="1"
        placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"
        class="textarea"
        @keydown.enter.exact.prevent="submit"
      />
      <button class="send" :disabled="sending || !text.trim()" @click="submit">
        {{ sending ? '…' : '发送' }}
      </button>
    </div>
    <div class="status" :class="connected ? 'ok' : 'pending'">
      {{ connected ? '● 已连接' : '○ 连接中…' }}
    </div>
  </div>
</template>

<style scoped>
.input-bar {
  border-top: 1px solid var(--border);
  padding: 0.7rem 0.8rem;
}

.row {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
}

.textarea {
  flex: 1;
  resize: none;
  max-height: 8rem;
  background: var(--surface-3);
  border: 1px solid var(--border);
  border-radius: 0.7rem;
  padding: 0.55rem 0.7rem;
  color: var(--text);
  font-size: 0.9rem;
}

.textarea:focus {
  outline: none;
  border-color: var(--primary);
}

.send {
  background: var(--primary);
  color: var(--on-primary);
  border-radius: 0.7rem;
  padding: 0.55rem 1rem;
  font-size: 0.9rem;
}

.send:disabled {
  opacity: 0.4;
}

.status {
  margin-top: 0.4rem;
  font-size: 0.72rem;
}

.status.ok {
  color: var(--success);
}

.status.pending {
  color: var(--warning);
}
</style>
