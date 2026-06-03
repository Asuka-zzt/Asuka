<script setup lang="ts">
import { storeToRefs } from 'pinia'

import { useUiStore } from '@/stores/ui'
import HealthBadge from './HealthBadge.vue'

const ui = useUiStore()
const { theme } = storeToRefs(ui)
</script>

<template>
  <header class="app-header">
    <div class="brand">
      <span class="brand-name">Asuka</span>
    </div>
    <nav class="nav">
      <RouterLink to="/" class="nav-link">Chat</RouterLink>
      <RouterLink to="/agent" class="nav-link">Agent 测试台</RouterLink>
      <RouterLink to="/wiki" class="nav-link">Wiki 生成</RouterLink>
    </nav>
    <div class="actions">
      <button
        type="button"
        class="theme-toggle"
        :title="theme === 'dark' ? '切换到白天模式' : '切换到夜晚模式'"
        :aria-label="theme === 'dark' ? '切换到白天模式' : '切换到夜晚模式'"
        @click="ui.toggleTheme()"
      >
        {{ theme === 'dark' ? '☀️' : '🌙' }}
      </button>
      <HealthBadge />
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid var(--border);
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
  flex-wrap: wrap;
  justify-content: center;
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
  background: var(--surface-2);
}

.nav-link.router-link-exact-active {
  opacity: 1;
  color: var(--primary);
  background: var(--primary-soft);
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.9rem;
  height: 1.9rem;
  border-radius: 9999px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-size: 0.9rem;
  line-height: 1;
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.theme-toggle:hover {
  background: var(--primary-soft);
  transform: translateY(-1px);
}

@media (max-width: 640px) {
  .brand-sub {
    display: none;
  }

  .nav-link {
    padding: 0.32rem 0.5rem;
    font-size: 0.78rem;
  }
}
</style>
