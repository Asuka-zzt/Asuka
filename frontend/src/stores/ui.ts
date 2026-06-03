import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const THEME_STORAGE_KEY = 'asuka-theme'

function applyTheme(mode: ThemeMode): void {
  document.documentElement.classList.toggle('dark', mode === 'dark')
}

// The pre-paint script in index.html already set the class; mirror it into state.
function initialTheme(): ThemeMode {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export const useUiStore = defineStore('ui', () => {
  const title = ref('Asuka')
  const theme = ref<ThemeMode>(initialTheme())

  function setTheme(mode: ThemeMode): void {
    theme.value = mode
    applyTheme(mode)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, mode)
    }
    catch {
      // Ignore storage failures (private mode / disabled storage).
    }
  }

  function toggleTheme(): void {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { title, theme, setTheme, toggleTheme }
})
