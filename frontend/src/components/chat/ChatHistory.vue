<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { nextTick, ref, watch } from 'vue'

import { useChatStore } from '@/stores/chat'
import MessageBubble from './MessageBubble.vue'

const { messages } = storeToRefs(useChatStore())
const scroller = ref<HTMLDivElement>()

// 内容变化时滚到底部
watch(
  () => messages.value.map(m => m.content).join('|'),
  async () => {
    await nextTick()
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
  },
)
</script>

<template>
  <div ref="scroller" class="history">
    <div v-if="!messages.length" class="empty">
      和 Asuka 打个招呼吧～<br>也可以说「给 ref/xxx 生成 wiki」。
    </div>
    <MessageBubble v-for="m in messages" :key="m.id" :message="m" />
  </div>
</template>

<style scoped>
.history {
  height: 100%;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.empty {
  margin: auto;
  text-align: center;
  font-size: 0.85rem;
  opacity: 0.4;
  line-height: 1.8;
}
</style>
