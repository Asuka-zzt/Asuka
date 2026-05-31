import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getHealth } from '@/api/client'

// 轮询 GET /health，驱动 Header 健康徽标。
export const useHealthStore = defineStore('health', () => {
  const online = ref(false)
  const version = ref('')
  let timer: ReturnType<typeof setInterval> | undefined

  async function poll() {
    try {
      const data = await getHealth()
      online.value = data.status === 'ok'
      version.value = data.version
    }
    catch {
      online.value = false
    }
  }

  function start() {
    void poll()
    timer = setInterval(() => void poll(), 5000)
  }

  function stop() {
    if (timer)
      clearInterval(timer)
    timer = undefined
  }

  return { online, version, poll, start, stop }
})
