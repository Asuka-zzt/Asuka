<script setup lang="ts">
import type { VoiceState } from '@/types/realtime'

const props = defineProps<{
  state: VoiceState
  supported: boolean
}>()

const emit = defineEmits<{
  start: []
  stop: []
}>()

function toggle() {
  if (props.state === 'listening' || props.state === 'transcribing')
    emit('stop')
  else
    emit('start')
}
</script>

<template>
  <button
    class="voice"
    :class="{ active: state === 'listening' || state === 'transcribing' }"
    :disabled="!supported || state === 'connecting'"
    :title="supported ? '语音输入' : '当前浏览器不支持实时语音'"
    type="button"
    @click="toggle"
  >
    <span v-if="state === 'connecting'">…</span>
    <span v-else-if="state === 'listening' || state === 'transcribing'">■</span>
    <span v-else>Mic</span>
  </button>
</template>

<style scoped>
.voice {
  width: 2.35rem;
  height: 2.35rem;
  border: 1px solid var(--border);
  border-radius: 0.7rem;
  background: var(--surface-3);
  color: var(--text);
  font-size: 0.95rem;
}

.voice.active {
  border-color: var(--primary);
  color: var(--primary);
}

.voice:disabled {
  opacity: 0.35;
}
</style>
