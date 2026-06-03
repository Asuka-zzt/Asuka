<script setup lang="ts">
import type { AgentInfo } from '@/types/chat'

import { ref } from 'vue'

import { postChat } from '@/api/client'

// 默认 Agent：后端硬编码、无 GET 接口，前端只读展示（对齐 core/agent/model.py 默认值）。
const agent: AgentInfo = {
  id: 'default',
  name: 'Asuka',
  soul: '你是 Asuka，一个友好、简洁、乐于助人的 AI 助手。',
  modelId: 'deepseek-chat',
}

const conversationId = ref('test-conv')
const message = ref('给 ref/normal_agent/astrbot/astrbot/core/pipeline 生成 wiki')
const reply = ref('')
const loading = ref(false)
const error = ref('')

async function send() {
  if (!message.value.trim() || loading.value)
    return
  loading.value = true
  error.value = ''
  reply.value = ''
  try {
    const res = await postChat(conversationId.value, message.value)
    reply.value = res.reply
  }
  catch (e) {
    error.value = (e as Error).message
  }
  finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="container">
      <!-- 默认人格（只读） -->
      <section class="card">
        <div class="card-title">默认 Agent（只读）</div>
        <div class="grid">
          <div><span class="label">名称</span>{{ agent.name }}</div>
          <div><span class="label">模型</span>{{ agent.modelId }}</div>
        </div>
        <div class="soul"><span class="label">Soul</span>{{ agent.soul }}</div>
        <div class="hint">ⓘ 后端暂无 Agent 配置接口，字段不可保存（待 DB 层）。</div>
      </section>

      <!-- 非流式测试 POST /chat -->
      <section class="card">
        <div class="card-title">非流式测试（POST /chat）</div>
        <label class="field">
          <span class="label">会话 ID</span>
          <input v-model="conversationId" class="input">
        </label>
        <label class="field">
          <span class="label">消息</span>
          <textarea v-model="message" rows="3" class="input" />
        </label>
        <button class="btn" :disabled="loading || !message.trim()" @click="send">
          {{ loading ? '发送中…' : '发送' }}
        </button>
        <div v-if="error" class="err">
          错误：{{ error }}
        </div>
        <div v-if="reply" class="reply">
          <div class="label">回复</div>
          <div class="reply-text">{{ reply }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  overflow-y: auto;
  padding: 1.5rem 1rem;
  display: flex;
  justify-content: center;
}

.container {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.card {
  background: var(--surface-translucent);
  border: 1px solid var(--border);
  border-radius: 1rem;
  padding: 1.1rem 1.2rem;
}

.card-title {
  font-weight: 600;
  margin-bottom: 0.85rem;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  font-size: 0.9rem;
}

.soul {
  font-size: 0.9rem;
  margin-top: 0.6rem;
  line-height: 1.6;
}

.label {
  display: inline-block;
  opacity: 0.5;
  font-size: 0.72rem;
  margin-right: 0.5rem;
}

.hint {
  font-size: 0.72rem;
  opacity: 0.5;
  margin-top: 0.6rem;
}

.field {
  display: block;
  margin-bottom: 0.85rem;
}

.input {
  width: 100%;
  margin-top: 0.35rem;
  background: var(--surface-3);
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  padding: 0.5rem 0.65rem;
  color: var(--text);
  font-size: 0.9rem;
  font-family: inherit;
  resize: vertical;
}

.input:focus {
  outline: none;
  border-color: var(--primary);
}

.btn {
  background: var(--primary);
  color: var(--on-primary);
  border-radius: 0.6rem;
  padding: 0.55rem 1.2rem;
  font-size: 0.9rem;
}

.btn:disabled {
  opacity: 0.4;
}

.err {
  color: var(--danger);
  font-size: 0.85rem;
  margin-top: 0.75rem;
}

.reply {
  margin-top: 0.85rem;
  background: var(--surface);
  border-radius: 0.7rem;
  padding: 0.75rem 0.8rem;
}

.reply-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.88rem;
  line-height: 1.6;
  margin-top: 0.3rem;
}
</style>
