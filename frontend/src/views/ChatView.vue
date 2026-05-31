<script setup lang="ts">
import ChatPanel from '@/components/chat/ChatPanel.vue'
import Live2DStage from '@/components/stage/Live2DStage.vue'
import StageLayout from '@/layouts/StageLayout.vue'
</script>

<template>
  <StageLayout>
    <template #stage>
      <Live2DStage />
    </template>
    <template #panel>
      <ChatPanel />
    </template>
  </StageLayout>
</template>
