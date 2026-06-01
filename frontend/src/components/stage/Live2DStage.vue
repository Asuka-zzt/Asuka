<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useLive2D } from '@/composables/useLive2D'
import StagePlaceholder from './StagePlaceholder.vue'

defineProps<{ modelUrl?: string }>()

const stageRef = ref<HTMLDivElement>()
const { state } = useLive2D(stageRef) // 本期 state 恒为 'placeholder'

onMounted(() => {
  // 本期：不挂载，显示占位。
  // 未来：modelUrl 存在时 mount(modelUrl)，把透明 Pixi 画布填入 stageRef。
})
</script>

<template>
  <!-- 这个容器就是 Live2D 的「空位」：透明、填满左舞台、未来 canvas 挂这里 -->
  <div ref="stageRef" class="live2d-stage">
    <StagePlaceholder v-if="state === 'placeholder'" />
  </div>
</template>

<style scoped>
.live2d-stage {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
</style>
