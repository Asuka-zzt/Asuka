<script setup lang="ts">
import AppHeader from '@/components/layout/AppHeader.vue'
</script>

<template>
  <div class="app-root">
    <AppHeader />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-root {
  height: 100dvh;
  width: 100vw;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
