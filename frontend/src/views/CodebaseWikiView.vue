<script setup lang="ts">
import type { GenerateWikiRequest, GenerateWikiResponse, WikiFile, WikiLanguage } from '@/types/wiki'

import { computed, nextTick, ref, watch } from 'vue'

import { generateWiki, postChat } from '@/api/client'

type SourceType = 'repo' | 'local'

interface MarkdownBlock {
  type: 'heading' | 'paragraph' | 'list' | 'code' | 'quote' | 'hr'
  level?: number
  html?: string
  items?: string[]
  language?: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const defaultInclude = [
  '*.c',
  '*.cc',
  '*.cpp',
  '*.go',
  '*.h',
  '*.java',
  '*.js',
  '*.jsx',
  '*.md',
  '*.php',
  '*.py',
  '*.pyi',
  '*.rb',
  '*.rs',
  '*.rst',
  '*.toml',
  '*.ts',
  '*.tsx',
  '*.yaml',
  '*.yml',
  'Dockerfile',
  'Makefile',
]

const defaultExclude = ['*.lock', '*.log', '*_test.*', 'test_*']

const sourceType = ref<SourceType>('local')
const repo = ref('')
const token = ref('')
const localDir = ref('')
const name = ref('')
const includeText = ref(defaultInclude.join('\n'))
const excludeText = ref(defaultExclude.join('\n'))
const maxSize = ref(100000)
const output = ref('output')
const language = ref<WikiLanguage>('chinese')
const maxAbstractions = ref(10)
const noCache = ref(false)
const loading = ref(false)
const error = ref('')
const result = ref<GenerateWikiResponse | null>(null)
const currentFilePath = ref('')
const copied = ref('')

const chatMessages = ref<ChatMessage[]>([
  {
    role: 'assistant',
    content: '生成 Wiki 后，可以在这里询问项目结构、模块职责或下一步修改建议。当前使用普通对话，后续可升级为 RAG。',
  },
])
const chatInput = ref('')
const chatLoading = ref(false)
const chatError = ref('')
const chatList = ref<HTMLElement>()

const canSubmit = computed(() => {
  const hasSource = sourceType.value === 'repo'
    ? Boolean(repo.value.trim())
    : Boolean(localDir.value.trim())
  return hasSource && maxSize.value > 0 && maxAbstractions.value > 0 && !loading.value
})

const orderedFiles = computed(() => {
  const files = result.value?.files ?? []
  return [...files].sort((a, b) => {
    if (a.path === 'index.md')
      return -1
    if (b.path === 'index.md')
      return 1
    return a.path.localeCompare(b.path)
  })
})

const currentFile = computed(() => {
  return orderedFiles.value.find(file => file.path === currentFilePath.value)
    ?? orderedFiles.value[0]
    ?? null
})

const currentBlocks = computed(() => {
  if (!currentFile.value)
    return []
  return renderMarkdown(currentFile.value.content)
})

const documentNav = computed(() => {
  return orderedFiles.value.map(file => ({
    path: file.path,
    title: file.path === 'index.md' ? '项目总览' : extractTitle(file),
    size: formatSize(file.size),
  }))
})

const activeTitle = computed(() => {
  if (!currentFile.value)
    return '在线预览'
  return currentFile.value.path === 'index.md' ? '项目总览' : extractTitle(currentFile.value)
})

watch(result, (value) => {
  currentFilePath.value = value?.files.find(file => file.path === 'index.md')?.path
    ?? value?.files[0]?.path
    ?? ''
})

function splitPatterns(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map(item => item.trim())
    .filter(Boolean)
}

function buildPayload(): GenerateWikiRequest {
  const payload: GenerateWikiRequest = {
    include: splitPatterns(includeText.value),
    exclude: splitPatterns(excludeText.value),
    max_size: maxSize.value,
    output: output.value.trim() || 'output',
    language: language.value,
    max_abstractions: maxAbstractions.value,
    no_cache: noCache.value,
  }
  if (name.value.trim())
    payload.name = name.value.trim()
  if (sourceType.value === 'repo') {
    payload.repo = repo.value.trim()
    if (token.value.trim())
      payload.token = token.value.trim()
  }
  else {
    payload.dir = localDir.value.trim()
  }
  return payload
}

async function submit() {
  if (!canSubmit.value)
    return
  loading.value = true
  error.value = ''
  copied.value = ''
  try {
    result.value = await generateWiki(buildPayload())
  }
  catch (e) {
    result.value = null
    error.value = (e as Error).message
  }
  finally {
    loading.value = false
  }
}

async function sendQuestion() {
  const message = chatInput.value.trim()
  if (!message || chatLoading.value)
    return
  chatInput.value = ''
  chatError.value = ''
  chatMessages.value.push({ role: 'user', content: message })
  chatLoading.value = true
  await scrollChatToBottom()
  try {
    const conversationId = `wiki-${result.value?.project_name ?? 'preview'}`
    const response = await postChat(conversationId, message)
    chatMessages.value.push({ role: 'assistant', content: response.reply })
  }
  catch (e) {
    chatError.value = (e as Error).message
  }
  finally {
    chatLoading.value = false
    await scrollChatToBottom()
  }
}

async function scrollChatToBottom() {
  await nextTick()
  if (chatList.value)
    chatList.value.scrollTop = chatList.value.scrollHeight
}

function formatSize(size: number): string {
  if (size < 1024)
    return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}

function extractTitle(file: WikiFile): string {
  const heading = file.content
    .split(/\r?\n/)
    .map(line => line.trim())
    .find(line => line.startsWith('# '))
  if (heading)
    return heading.replace(/^#+\s*/, '').trim()
  return file.path.replace(/\.md$/i, '').replace(/^\d+_/, '').replace(/[_-]+/g, ' ')
}

async function copyOutputPath() {
  if (!result.value)
    return
  await navigator.clipboard.writeText(result.value.output_dir)
  copied.value = 'output'
}

function handleDrop(event: DragEvent) {
  const text = event.dataTransfer?.getData('text/plain')?.trim()
  if (text)
    localDir.value = text
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function renderInline(value: string): string {
  let html = escapeHtml(value)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
    const safeHref = escapeHtml(href)
    return `<a href="${safeHref}" target="_blank" rel="noreferrer">${label}</a>`
  })
  return html
}

function renderMarkdown(markdown: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = []
  const lines = markdown.split(/\r?\n/)
  let paragraph: string[] = []
  let listItems: string[] = []
  let codeLines: string[] = []
  let codeLanguage = ''
  let inCode = false

  function flushParagraph() {
    if (!paragraph.length)
      return
    blocks.push({ type: 'paragraph', html: renderInline(paragraph.join(' ')) })
    paragraph = []
  }

  function flushList() {
    if (!listItems.length)
      return
    blocks.push({ type: 'list', items: listItems.map(renderInline) })
    listItems = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    const fence = trimmed.match(/^```(.*)$/)
    if (fence) {
      if (inCode) {
        blocks.push({
          type: 'code',
          language: codeLanguage,
          html: escapeHtml(codeLines.join('\n')),
        })
        codeLines = []
        codeLanguage = ''
        inCode = false
      }
      else {
        flushParagraph()
        flushList()
        inCode = true
        codeLanguage = fence[1]?.trim() ?? ''
      }
      continue
    }

    if (inCode) {
      codeLines.push(line)
      continue
    }

    if (!trimmed) {
      flushParagraph()
      flushList()
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      flushList()
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        html: renderInline(heading[2]),
      })
      continue
    }

    if (/^[-*_]{3,}$/.test(trimmed)) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'hr' })
      continue
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/)
    if (bullet) {
      flushParagraph()
      listItems.push(bullet[1])
      continue
    }

    if (trimmed.startsWith('>')) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'quote', html: renderInline(trimmed.replace(/^>\s?/, '')) })
      continue
    }

    flushList()
    paragraph.push(trimmed)
  }

  if (inCode) {
    blocks.push({ type: 'code', language: codeLanguage, html: escapeHtml(codeLines.join('\n')) })
  }
  flushParagraph()
  flushList()
  return blocks
}
</script>

<template>
  <div class="wiki-workspace">
    <aside class="sidebar">
      <div class="project-mark">
        <div class="mark-icon">
          W
        </div>
        <div>
          <strong>Code Wiki</strong>
          <span>{{ result?.project_name ?? '生成项目文档' }}</span>
        </div>
      </div>

      <section class="source-box">
        <div class="box-head">
          <span>Source</span>
          <div class="segmented">
            <button
              :class="['segment', { active: sourceType === 'local' }]"
              type="button"
              @click="sourceType = 'local'"
            >
              Local
            </button>
            <button
              :class="['segment', { active: sourceType === 'repo' }]"
              type="button"
              @click="sourceType = 'repo'"
            >
              GitHub
            </button>
          </div>
        </div>

        <label v-if="sourceType === 'local'" class="field">
          <span>Local directory</span>
          <input
            v-model="localDir"
            class="control"
            placeholder="/path/to/project"
            autocomplete="off"
          >
        </label>
        <div
          v-if="sourceType === 'local'"
          class="drop-zone"
          @dragover.prevent
          @drop.prevent="handleDrop"
        >
          可拖入路径文本
        </div>

        <template v-else>
          <label class="field">
            <span>Repository URL</span>
            <input
              v-model="repo"
              class="control"
              placeholder="https://github.com/owner/repo"
              autocomplete="off"
            >
          </label>
          <label class="field">
            <span>Token</span>
            <input
              v-model="token"
              class="control"
              type="password"
              placeholder="private repo optional"
              autocomplete="off"
            >
          </label>
        </template>

        <div class="compact-grid">
          <label class="field">
            <span>Name</span>
            <input v-model="name" class="control" placeholder="auto">
          </label>
          <label class="field">
            <span>Language</span>
            <select v-model="language" class="control">
              <option value="chinese">
                中文
              </option>
              <option value="english">
                English
              </option>
            </select>
          </label>
        </div>

        <details class="advanced">
          <summary>高级参数</summary>
          <label class="field">
            <span>Output</span>
            <input v-model="output" class="control" placeholder="output">
          </label>
          <div class="compact-grid">
            <label class="field">
              <span>Max size</span>
              <input v-model.number="maxSize" class="control" type="number" min="1">
            </label>
            <label class="field">
              <span>Chapters</span>
              <input v-model.number="maxAbstractions" class="control" type="number" min="1">
            </label>
          </div>
          <label class="field">
            <span>Include</span>
            <textarea v-model="includeText" class="control textarea" rows="5" />
          </label>
          <label class="field">
            <span>Exclude</span>
            <textarea v-model="excludeText" class="control textarea" rows="4" />
          </label>
          <label class="check-field">
            <input v-model="noCache" type="checkbox">
            <span>禁用缓存</span>
          </label>
        </details>

        <button class="primary-btn" :disabled="!canSubmit" type="button" @click="submit">
          {{ loading ? '生成中...' : '生成 Wiki' }}
        </button>
        <p v-if="error" class="error-text">
          {{ error }}
        </p>
      </section>

      <section class="toc">
        <div class="toc-title">
          On this page
        </div>
        <button
          v-for="item in documentNav"
          :key="item.path"
          :class="['toc-item', { active: item.path === currentFilePath }]"
          type="button"
          @click="currentFilePath = item.path"
        >
          <span>{{ item.title }}</span>
          <small>{{ item.size }}</small>
        </button>
        <div v-if="!documentNav.length" class="toc-empty">
          生成后这里会显示文档目录
        </div>
      </section>

      <div v-if="result" class="meta-box">
        <span>Output</span>
        <button type="button" @click="copyOutputPath">
          {{ copied === 'output' ? '已复制' : result.output_dir }}
        </button>
      </div>
    </aside>

    <main class="reader">
      <div class="reader-toolbar">
        <div>
          <p class="eyebrow">
            {{ result?.project_name ?? 'Preview' }}
          </p>
          <h1>{{ activeTitle }}</h1>
        </div>
        <span v-if="loading" class="status running">Running</span>
        <span v-else-if="result" class="status success">Ready</span>
      </div>

      <div v-if="loading" class="empty-reader">
        <div class="spark">
          ✦
        </div>
        <h2>正在生成项目 Wiki</h2>
        <p>分析文件、抽象模块并写入章节时会短暂停顿。</p>
      </div>

      <article v-else-if="currentFile" class="markdown-body">
        <template v-for="(block, index) in currentBlocks" :key="index">
          <component
            :is="`h${Math.min(block.level ?? 2, 4)}`"
            v-if="block.type === 'heading'"
            v-html="block.html"
          />
          <p v-else-if="block.type === 'paragraph'" v-html="block.html" />
          <blockquote v-else-if="block.type === 'quote'" v-html="block.html" />
          <hr v-else-if="block.type === 'hr'">
          <ul v-else-if="block.type === 'list'">
            <li v-for="(item, itemIndex) in block.items" :key="itemIndex" v-html="item" />
          </ul>
          <pre v-else-if="block.type === 'code'"><code v-html="block.html" /></pre>
        </template>
      </article>

      <div v-else class="empty-reader">
        <div class="spark">
          ✦
        </div>
        <h2>选择代码来源并生成 Wiki</h2>
        <p>生成完成后，中间区域会直接显示 Markdown 文档内容。</p>
      </div>
    </main>

    <aside class="chat-panel">
      <div class="chat-head">
        <div class="spark small">
          ✦
        </div>
        <div>
          <h2>项目 AI 对话</h2>
          <p>普通对话模式</p>
        </div>
      </div>

      <div ref="chatList" class="chat-list">
        <div
          v-for="(message, index) in chatMessages"
          :key="index"
          :class="['chat-message', message.role]"
        >
          {{ message.content }}
        </div>
        <div v-if="chatLoading" class="chat-message assistant">
          正在回复...
        </div>
      </div>

      <p v-if="chatError" class="chat-error">
        {{ chatError }}
      </p>

      <form class="chat-input" @submit.prevent="sendQuestion">
        <input
          v-model="chatInput"
          placeholder="Ask about this repository"
          autocomplete="off"
        >
        <button :disabled="!chatInput.trim() || chatLoading" type="submit">
          发送
        </button>
      </form>
    </aside>
  </div>
</template>

<style scoped>
.wiki-workspace {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 19rem minmax(0, 1fr) 24rem;
  gap: 0;
  background: var(--bg);
  color: var(--text);
}

.sidebar,
.chat-panel {
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  background: var(--bg);
}

.sidebar {
  border-right: 1px solid var(--border);
}

.chat-panel {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border);
}

.project-mark {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.mark-icon,
.spark {
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #5ff0b4, #6f8cff 55%, #ff8db6);
  color: #fff;
  font-weight: 800;
}

.mark-icon {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.45rem;
}

.project-mark strong,
.chat-head h2 {
  display: block;
  margin: 0;
  font-size: 1.2rem;
}

.project-mark span,
.chat-head p {
  display: block;
  margin: 0.1rem 0 0;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.source-box,
.toc,
.meta-box {
  margin-top: 1rem;
}

.box-head,
.compact-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 0.75rem;
}

.box-head {
  margin-bottom: 0.8rem;
  color: var(--text-muted);
  font-weight: 700;
}

.segmented {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  padding: 0.16rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface-3);
}

.segment {
  min-width: 3.8rem;
  padding: 0.34rem 0.5rem;
  border-radius: 0.35rem;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.segment.active {
  background: var(--primary);
  color: var(--on-primary);
}

.field {
  display: grid;
  gap: 0.35rem;
  margin-bottom: 0.7rem;
  color: var(--text-muted);
  font-size: 0.76rem;
}

.control,
.chat-input input {
  width: 100%;
  min-height: 2.35rem;
  border: 1px solid var(--border-strong);
  border-radius: 0.5rem;
  background: var(--surface);
  color: var(--text);
  font: inherit;
}

.control {
  padding: 0.5rem 0.6rem;
}

.control:focus,
.chat-input input:focus {
  outline: none;
  border-color: var(--primary);
}

.textarea {
  min-height: 7rem;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.75rem;
  line-height: 1.45;
}

.drop-zone {
  margin: -0.25rem 0 0.75rem;
  padding: 0.65rem;
  border: 1px dashed var(--primary-soft);
  border-radius: 0.5rem;
  color: var(--text-faint);
  text-align: center;
  font-size: 0.76rem;
}

.advanced {
  margin: 0.25rem 0 0.8rem;
  color: var(--text-muted);
}

.advanced summary {
  cursor: pointer;
  margin-bottom: 0.65rem;
  font-size: 0.82rem;
  font-weight: 700;
}

.check-field {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0.2rem 0 0.85rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.primary-btn,
.chat-input button,
.meta-box button {
  width: 100%;
  min-height: 2.45rem;
  border-radius: 0.5rem;
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 800;
}

.primary-btn:disabled,
.chat-input button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.error-text,
.chat-error {
  color: var(--danger);
  font-size: 0.78rem;
  line-height: 1.5;
}

.toc {
  padding-top: 0.8rem;
  border-top: 1px solid var(--border);
}

.toc-title {
  margin-bottom: 0.6rem;
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 800;
}

.toc-item {
  width: 100%;
  display: grid;
  gap: 0.25rem;
  padding: 0.62rem 0.75rem;
  border-left: 2px solid transparent;
  background: transparent;
  color: var(--text);
  text-align: left;
}

.toc-item.active {
  border-left-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
}

.toc-item span {
  line-height: 1.25;
}

.toc-item small,
.toc-empty {
  color: var(--text-faint);
  font-size: 0.72rem;
}

.meta-box {
  display: grid;
  gap: 0.4rem;
  color: var(--text-faint);
  font-size: 0.72rem;
}

.meta-box button {
  overflow: hidden;
  padding: 0 0.65rem;
  background: var(--surface-2);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.reader {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  background: var(--surface-3);
}

.reader-toolbar,
.markdown-body,
.empty-reader {
  width: min(58rem, 100%);
  margin: 0 auto;
}

.reader-toolbar {
  min-height: 4rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.eyebrow {
  margin: 0 0 0.25rem;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.reader-toolbar h1 {
  margin: 0;
  font-size: 1.55rem;
  line-height: 1.2;
}

.status {
  padding: 0.32rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 800;
}

.status.running {
  background: var(--primary-soft);
  color: var(--primary);
}

.status.success {
  background: color-mix(in srgb, var(--success) 16%, transparent);
  color: var(--success);
}

.markdown-body {
  padding: 2rem;
  border: 1px solid var(--border-strong);
  border-radius: 0.75rem;
  background: var(--surface);
  box-shadow: 0 18px 55px rgba(0, 0, 0, 0.28);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 1.4rem 0 0.7rem;
  line-height: 1.25;
}

.markdown-body :deep(h1:first-child),
.markdown-body :deep(h2:first-child),
.markdown-body :deep(h3:first-child) {
  margin-top: 0;
}

.markdown-body :deep(h1) {
  font-size: 2rem;
}

.markdown-body :deep(h2) {
  padding-top: 0.7rem;
  border-top: 1px solid var(--border);
  font-size: 1.35rem;
}

.markdown-body :deep(h3) {
  font-size: 1.08rem;
}

.markdown-body p,
.markdown-body li,
.markdown-body blockquote {
  color: var(--text);
  font-size: 0.95rem;
  line-height: 1.75;
}

.markdown-body ul {
  margin: 0.6rem 0 1rem;
  padding-left: 1.2rem;
}

.markdown-body blockquote {
  margin: 1rem 0;
  padding: 0.7rem 0.9rem;
  border-left: 3px solid var(--primary);
  background: var(--primary-softer);
}

.markdown-body pre {
  overflow-x: auto;
  padding: 1rem;
  border-radius: 0.5rem;
  background: var(--surface-3);
}

.markdown-body code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.markdown-body p code,
.markdown-body li code {
  padding: 0.12rem 0.28rem;
  border-radius: 0.3rem;
  background: var(--surface-2);
}

.markdown-body :deep(a) {
  color: var(--primary);
}

.empty-reader {
  min-height: 30rem;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 0.65rem;
  border: 1px solid var(--border-strong);
  border-radius: 0.75rem;
  background: var(--surface);
  text-align: center;
}

.empty-reader h2 {
  margin: 0;
  font-size: 1.35rem;
}

.empty-reader p {
  margin: 0;
  color: var(--text-muted);
}

.spark {
  width: 4rem;
  height: 4rem;
  border-radius: 999px;
  font-size: 2.2rem;
}

.spark.small {
  width: 2.4rem;
  height: 2.4rem;
  flex: 0 0 auto;
  font-size: 1.25rem;
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  padding: 1rem 0;
}

.chat-message {
  max-width: 88%;
  padding: 0.72rem 0.82rem;
  border-radius: 0.65rem;
  color: var(--text);
  font-size: 0.9rem;
  line-height: 1.55;
  white-space: pre-wrap;
}

.chat-message.assistant {
  align-self: flex-start;
  background: var(--surface-2);
}

.chat-message.user {
  align-self: flex-end;
  background: var(--primary);
  color: var(--on-primary);
}

.chat-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 4.5rem;
  gap: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.chat-input input {
  padding: 0.6rem 0.8rem;
}

.chat-input button {
  min-height: 2.6rem;
}

@media (max-width: 1180px) {
  .wiki-workspace {
    grid-template-columns: 17rem minmax(0, 1fr);
  }

  .chat-panel {
    grid-column: 1 / -1;
    min-height: 22rem;
    border-left: none;
    border-top: 1px solid var(--border);
  }
}

@media (max-width: 760px) {
  .wiki-workspace {
    display: block;
    overflow-y: auto;
  }

  .sidebar,
  .reader,
  .chat-panel {
    overflow: visible;
    border: none;
  }

  .reader-toolbar,
  .markdown-body,
  .empty-reader {
    width: 100%;
  }

  .markdown-body {
    padding: 1rem;
  }

  .compact-grid,
  .box-head {
    grid-template-columns: 1fr;
  }
}
</style>
