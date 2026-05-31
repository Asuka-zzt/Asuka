<script setup lang="ts">
import HealthBadge from './HealthBadge.vue'
</script>

<template>
  <header class="app-header">
    <div class="brand">
      <span class="brand-name">AsukaBot</span>
      <span class="brand-sub">多人格 AI</span>
    </div>
    <nav class="nav">
      <RouterLink to="/" class="nav-link">Chat</RouterLink>
      <RouterLink to="/agent" class="nav-link">Agent 测试台</RouterLink>
    </nav>
    <HealthBadge />
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.brand-name {
  font-size: 1.05rem;
  font-weight: 600;
}

.brand-sub {
  font-size: 0.72rem;
  opacity: 0.5;
}

.nav {
  display: flex;
  gap: 0.25rem;
}

.nav-link {
  padding: 0.35rem 0.7rem;
  border-radius: 0.5rem;
  font-size: 0.85rem;
  opacity: 0.7;
}

.nav-link:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.06);
}

.nav-link.router-link-exact-active {
  opacity: 1;
  color: #cfc8ff;
  background: rgba(124, 108, 240, 0.18);
}
</style>
