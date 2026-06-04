<script setup lang="ts">
import type { VoiceState } from '@/types/realtime'
import type { Ref } from 'vue'

import { storeToRefs } from 'pinia'
import { ref } from 'vue'

import { useRealtimeVoice } from '@/composables/useRealtimeVoice'
import { useChatSocket } from '@/composables/useChatSocket'
import { useChatStore } from '@/stores/chat'
import ChatHistory from './ChatHistory.vue'
import ChatInput from './ChatInput.vue'

const store = useChatStore()
const { connected, sending } = storeToRefs(store)
const realtimeEnabled = import.meta.env.VITE_REALTIME_VOICE !== '0'
let voiceState: Ref<VoiceState> = ref('idle')
let voiceSupported: Ref<boolean> = ref(false)
let interimTranscript: Ref<string> = ref('')
let startVoiceInput = () => {}
let stopVoiceInput = () => {}
let send: (text: string) => void

if (realtimeEnabled) {
  const realtime = useRealtimeVoice()
  send = realtime.send
  voiceState = realtime.voiceState
  voiceSupported = realtime.voiceSupported
  interimTranscript = realtime.interimTranscript
  startVoiceInput = realtime.startVoiceInput
  stopVoiceInput = realtime.stopVoiceInput
}
else {
  const socket = useChatSocket()
  send = socket.send
}
</script>

<template>
  <div class="chat-panel">
    <div class="history-wrap">
      <ChatHistory />
    </div>
    <ChatInput
      :sending="sending"
      :connected="connected"
      :voice-state="voiceState"
      :voice-supported="voiceSupported"
      :transcript="interimTranscript"
      @send="send"
      @start-voice="startVoiceInput"
      @stop-voice="stopVoiceInput"
    />
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
