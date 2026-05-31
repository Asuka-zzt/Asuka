import type { Ref } from 'vue'

import { ref } from 'vue'

export type Live2DState = 'placeholder' | 'loading' | 'mounted' | 'error'

// Live2D 挂载接口。本期为 stub：state 恒为 'placeholder'。
//
// TODO(live2d)：接入真实渲染时实现 mount —— 动态 import pixi.js 与
// pixi-live2d-display/cubism4，创建透明 Application({ backgroundAlpha: 0 })，
// Live2DModel.from(modelUrl)，把 view 以 width/height:100% objectFit:contain
// appendChild 到 container（参考 AIRI live2d/Canvas.vue）。
export function useLive2D(_container: Ref<HTMLDivElement | undefined>) {
  const state = ref<Live2DState>('placeholder')

  async function mount(_modelUrl: string): Promise<void> {
    // TODO(live2d)
  }

  function dispose(): void {
    // TODO(live2d)
  }

  return { state, mount, dispose }
}
