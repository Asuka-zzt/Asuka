import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import unocss from 'unocss/vite'
import { defineConfig } from 'vite'

// 后端默认 127.0.0.1:8000；dev 用 proxy 转发，避免 CORS。
export default defineConfig({
  plugins: [vue(), unocss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/chat': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
