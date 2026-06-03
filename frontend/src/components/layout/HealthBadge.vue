<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted, onUnmounted } from 'vue'

import { useHealthStore } from '@/stores/health'

const store = useHealthStore()
const { online, version } = storeToRefs(store)

onMounted(() => store.start())
onUnmounted(() => store.stop())
</script>

<template>
  <div class="badge">
    <span class="dot" :class="online ? 'on' : 'off'" />
    <span class="label">{{ online ? `在线 v${version}` : '离线' }}</span>
  </div>
</template>

<style scoped>
.badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
}

.dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 9999px;
}

.dot.on {
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
}

.dot.off {
  background: var(--text-faint);
}

.label {
  opacity: 0.7;
}
</style>
