/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}

declare module 'uno.css'

interface ImportMetaEnv {
  readonly VITE_WS_BASE?: string
  readonly VITE_API_BASE?: string
  readonly VITE_LIVE2D_MODEL_URL?: string
  readonly VITE_LIVE2D_CUBISM_CORE_URL?: string
  readonly VITE_LIVE2D_MODEL_SCALE?: string
  readonly VITE_LIVE2D_MODEL_OFFSET_X?: string
  readonly VITE_LIVE2D_MODEL_OFFSET_Y?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
