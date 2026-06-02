<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useLive2D } from '@/composables/useLive2D'
import { useLive2DStore } from '@/stores/live2d'
import StagePlaceholder from './StagePlaceholder.vue'

const props = defineProps<{ modelUrl?: string }>()

const stageRef = ref<HTMLDivElement>()
const configuredModelUrl = computed(() => props.modelUrl ?? import.meta.env.VITE_LIVE2D_MODEL_URL ?? '')
const live2dStore = useLive2DStore()
const { motionCommand, expressionCommand, mouthOpen } = storeToRefs(live2dStore)
const {
  state,
  error,
  expressionNames,
  mount,
  dispose,
  playMotion,
  setMouthOpen,
  setExpression,
  resetExpression,
} = useLive2D(stageRef)

function playCurrentMotion(): void {
  const command = motionCommand.value
  playMotion(command.group, command.index, command.fallbackGroups)
}

onMounted(() => {
  if (configuredModelUrl.value)
    void mount(configuredModelUrl.value)
})

watch(configuredModelUrl, (modelUrl) => {
  if (modelUrl)
    void mount(modelUrl)
  else {
    dispose()
    state.value = 'placeholder'
  }
})

watch(state, (nextState) => {
  if (nextState === 'mounted') {
    playCurrentMotion()
    live2dStore.setAvailableExpressions(expressionNames.value)
  }
})

watch(motionCommand, () => {
  if (state.value === 'mounted')
    playCurrentMotion()
}, { deep: true })

watch(mouthOpen, (value) => {
  if (state.value === 'mounted')
    setMouthOpen(value)
})

watch(expressionCommand, (command) => {
  if (state.value !== 'mounted')
    return
  if (!command) {
    resetExpression()
    return
  }
  setExpression(command.name, command.durationMs, command.intensity)
}, { deep: true })

watch(expressionNames, (names) => {
  live2dStore.setAvailableExpressions(names)
})
</script>

<template>
  <div ref="stageRef" class="live2d-stage">
    <StagePlaceholder
      v-if="state === 'placeholder'"
      title="Live2D 区域"
      hint="配置模型地址后自动挂载"
    />
    <div v-else-if="state === 'loading'" class="stage-status">
      <span class="spinner" />
      <span>Loading Live2D</span>
    </div>
    <StagePlaceholder
      v-else-if="state === 'error'"
      title="Live2D 加载失败"
      :hint="error || '请检查模型地址和资源路径'"
    />
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

.live2d-stage :deep(.live2d-canvas) {
  position: absolute;
  inset: 0;
}

.stage-status {
  position: absolute;
  inset: auto auto 1.25rem 50%;
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  transform: translateX(-50%);
  padding: 0.55rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  background: rgba(10, 9, 16, 0.72);
  color: rgba(232, 230, 240, 0.82);
  font-size: 0.82rem;
}

.spinner {
  width: 0.8rem;
  height: 0.8rem;
  border: 2px solid rgba(232, 230, 240, 0.28);
  border-top-color: #8ee8d3;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
