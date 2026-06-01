<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  hint?: string
}>(), {
  title: 'Live2D 区域',
  hint: '人物画布将挂载于此',
})
</script>

<template>
  <div class="placeholder">
    <div class="silhouette">
      <span class="spark">✦</span>
    </div>
    <div class="title">{{ title }}</div>
    <div class="hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  text-align: center;
  user-select: none;
}

.silhouette {
  width: min(38vh, 260px);
  height: min(60vh, 420px);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed rgba(124, 108, 240, 0.35);
  border-radius: 1.5rem;
  background: linear-gradient(180deg, rgba(124, 108, 240, 0.06), rgba(124, 108, 240, 0.01));
}

.spark {
  font-size: 3rem;
  opacity: 0.7;
}

.title {
  font-size: 0.85rem;
  opacity: 0.6;
}

.hint {
  font-size: 0.72rem;
  opacity: 0.4;
}
</style>
