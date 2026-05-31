<script setup lang="ts">
import { storeToRefs } from 'pinia'

import { useChatSocket } from '@/composables/useChatSocket'
import { useChatStore } from '@/stores/chat'
import ChatHistory from './ChatHistory.vue'
import ChatInput from './ChatInput.vue'

const store = useChatStore()
const { connected, sending } = storeToRefs(store)
const { send } = useChatSocket()
</script>

<template>
  <div class="chat-panel">
    <div class="history-wrap">
      <ChatHistory />
    </div>
    <ChatInput :sending="sending" :connected="connected" @send="send" />
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.history-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
