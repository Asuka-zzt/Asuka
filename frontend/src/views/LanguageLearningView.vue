<script setup lang="ts">
import type { PersonaId } from '@/types/language'

import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import ChatHistory from '@/components/chat/ChatHistory.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import Live2DStage from '@/components/stage/Live2DStage.vue'
import { useChatSocket } from '@/composables/useChatSocket'
import StageLayout from '@/layouts/StageLayout.vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const { connected, sending } = storeToRefs(store)
const { send } = useChatSocket()

const personaId = ref<PersonaId>('english_teacher')
const englishLevel = ref('B1')
const japaneseLevel = ref('N4')

const level = computed(() => personaId.value === 'english_teacher' ? englishLevel.value : japaneseLevel.value)

const levelOptions = computed(() =>
  personaId.value === 'english_teacher'
    ? ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    : ['N5', 'N4', 'N3', 'N2', 'N1'],
)

function sendLearningMessage(text: string) {
  send(text, {
    persona_id: personaId.value,
    level: level.value,
  })
}

function quickPrompt(kind: 'correct' | 'mcq' | 'cloze' | 'translation') {
  const lang = personaId.value === 'english_teacher' ? '英语' : '日语'
  const prompts = {
    correct: `请帮我批改这句${lang}：`,
    mcq: `请按 ${level.value} 水平出 5 道${lang}选择题，主题是日常对话。`,
    cloze: `请按 ${level.value} 水平出 5 道${lang}填空题，主题是日常对话。`,
    translation: `请按 ${level.value} 水平出 5 道中文到${lang}翻译题，主题是日常对话。`,
  }
  sendLearningMessage(prompts[kind])
}

function newLearningConversation() {
  store.resetConversation('edu')
}
</script>

<template>
  <StageLayout>
    <template #stage>
      <Live2DStage />
    </template>
    <template #panel>
      <div class="learning-panel">
        <div class="learning-toolbar">
          <div class="segmented">
            <button
              type="button"
              :class="{ active: personaId === 'english_teacher' }"
              @click="personaId = 'english_teacher'"
            >
              英语老师
            </button>
            <button
              type="button"
              :class="{ active: personaId === 'japanese_teacher' }"
              @click="personaId = 'japanese_teacher'"
            >
              日语老师
            </button>
          </div>
          <select v-if="personaId === 'english_teacher'" v-model="englishLevel" class="level-select">
            <option v-for="item in levelOptions" :key="item" :value="item">
              {{ item }}
            </option>
          </select>
          <select v-else v-model="japaneseLevel" class="level-select">
            <option v-for="item in levelOptions" :key="item" :value="item">
              {{ item }}
            </option>
          </select>
        </div>

        <div class="quick-actions">
          <button type="button" @click="quickPrompt('correct')">批改</button>
          <button type="button" @click="quickPrompt('mcq')">选择题</button>
          <button type="button" @click="quickPrompt('cloze')">填空题</button>
          <button type="button" @click="quickPrompt('translation')">翻译题</button>
          <button type="button" @click="newLearningConversation">新会话</button>
          <button type="button" disabled title="WebRTC 实时语音陪练按设计二期接入">语音模式</button>
        </div>

        <div class="history-wrap">
          <ChatHistory />
        </div>
        <ChatInput :sending="sending" :connected="connected" @send="sendLearningMessage" />
      </div>
    </template>
  </StageLayout>
</template>

<style scoped>
.learning-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.learning-toolbar {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0.8rem 0.45rem;
  border-bottom: 1px solid var(--border);
}

.segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.2rem;
  padding: 0.2rem;
  border-radius: 0.5rem;
  background: var(--surface-2);
}

.segmented button,
.quick-actions button,
.level-select {
  border: 1px solid var(--border);
  border-radius: 0.45rem;
  color: var(--text);
}

.segmented button {
  padding: 0.38rem 0.65rem;
  font-size: 0.84rem;
}

.segmented button.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.level-select {
  min-width: 5rem;
  padding: 0.4rem 0.55rem;
  background: var(--surface-2);
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0.45rem 0.8rem 0.6rem;
  border-bottom: 1px solid var(--border);
}

.quick-actions button {
  padding: 0.34rem 0.55rem;
  background: var(--surface-2);
  font-size: 0.78rem;
}

.quick-actions button:disabled {
  opacity: 0.45;
}

.history-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 640px) {
  .learning-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
