<script setup lang="ts">
// AIRI 式两栏：左舞台（Live2D 空位）/ 右面板（聊天）。移动端竖排。
</script>

<template>
  <div class="stage-layout">
    <section class="stage-area">
      <slot name="stage" />
    </section>
    <aside class="panel-area">
      <slot name="panel" />
    </aside>
  </div>
</template>

<style scoped>
.stage-layout {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  height: 100%;
  width: 100%;
}

.stage-area {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 1rem;
  overflow: hidden;
  background: linear-gradient(160deg, rgba(124, 108, 240, 0.10), rgba(124, 108, 240, 0.02));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.panel-area {
  display: flex;
  flex: 1;
  width: 100%;
  max-width: 500px;
  border-radius: 1rem;
  overflow: hidden;
  background: rgba(20, 18, 30, 0.55);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

@media (max-width: 768px) {
  .stage-layout {
    flex-direction: column;
  }

  .stage-area {
    flex: none;
    min-height: 28vh;
  }

  .panel-area {
    max-width: none;
    flex: 1;
  }
}
</style>
