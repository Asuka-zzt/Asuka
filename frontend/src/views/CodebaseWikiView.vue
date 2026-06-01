<script setup lang="ts">
import type { GenerateWikiRequest, GenerateWikiResponse, WikiLanguage } from '@/types/wiki'

import { computed, ref } from 'vue'

import { generateWiki } from '@/api/client'

type SourceType = 'repo' | 'local'

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

const sourceType = ref<SourceType>('repo')
const repo = ref('')
const token = ref('')
const localDir = ref('')
const name = ref('')
const includeText = ref(defaultInclude.join('\n'))
const excludeText = ref(defaultExclude.join('\n'))
const maxSize = ref(100000)
const output = ref('output')
const language = ref<WikiLanguage>('english')
const maxAbstractions = ref(10)
const noCache = ref(false)
const loading = ref(false)
const error = ref('')
const result = ref<GenerateWikiResponse | null>(null)
const copied = ref('')

const canSubmit = computed(() => {
  const hasSource = sourceType.value === 'repo'
    ? Boolean(repo.value.trim())
    : Boolean(localDir.value.trim())
  return hasSource && maxSize.value > 0 && maxAbstractions.value > 0 && !loading.value
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
  result.value = null
  try {
    result.value = await generateWiki(buildPayload())
  }
  catch (e) {
    error.value = (e as Error).message
  }
  finally {
    loading.value = false
  }
}

function formatSize(size: number): string {
  if (size < 1024)
    return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}

async function copyText(label: string, text: string) {
  await navigator.clipboard.writeText(text)
  copied.value = label
}

function handleDrop(event: DragEvent) {
  const text = event.dataTransfer?.getData('text/plain')?.trim()
  if (text)
    localDir.value = text
}
</script>

<template>
  <div class="wiki-page">
    <section class="hero">
      <div>
        <p class="eyebrow">
          Codebase2Wiki
        </p>
        <h1>把代码库生成可阅读 Wiki</h1>
      </div>
      <button class="primary-btn" :disabled="!canSubmit" @click="submit">
        {{ loading ? '生成中...' : '开始生成' }}
      </button>
    </section>

    <div class="content-grid">
      <section class="source-panel">
        <div class="panel-head">
          <h2>代码来源</h2>
          <div class="segmented">
            <button
              :class="['segment', { active: sourceType === 'repo' }]"
              type="button"
              @click="sourceType = 'repo'"
            >
              GitHub
            </button>
            <button
              :class="['segment', { active: sourceType === 'local' }]"
              type="button"
              @click="sourceType = 'local'"
            >
              Local
            </button>
          </div>
        </div>

        <div v-if="sourceType === 'repo'" class="field-stack">
          <label class="field">
            <span>Repo URL</span>
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
              placeholder="Private repo 可选"
              autocomplete="off"
            >
          </label>
        </div>

        <div v-else class="field-stack">
          <label class="field">
            <span>Local Dir</span>
            <input
              v-model="localDir"
              class="control"
              placeholder="/path/to/project"
              autocomplete="off"
            >
          </label>
          <div class="drop-zone" @dragover.prevent @drop.prevent="handleDrop">
            拖入路径文本，或填写后端服务可访问的本地目录
          </div>
        </div>
      </section>

      <section class="params-panel">
        <div class="panel-head">
          <h2>生成参数</h2>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>项目名</span>
            <input v-model="name" class="control" placeholder="留空自动推导">
          </label>
          <label class="field">
            <span>输出目录</span>
            <input v-model="output" class="control" placeholder="output">
          </label>
          <label class="field">
            <span>语言</span>
            <select v-model="language" class="control">
              <option value="english">
                English
              </option>
              <option value="chinese">
                中文
              </option>
            </select>
          </label>
          <label class="field">
            <span>最大文件大小</span>
            <input v-model.number="maxSize" class="control" type="number" min="1">
          </label>
          <label class="field">
            <span>最大抽象数</span>
            <input v-model.number="maxAbstractions" class="control" type="number" min="1">
          </label>
          <label class="check-field">
            <input v-model="noCache" type="checkbox">
            <span>禁用缓存</span>
          </label>
        </div>

        <div class="pattern-grid">
          <label class="field">
            <span>Include patterns</span>
            <textarea v-model="includeText" class="control textarea" rows="8" />
          </label>
          <label class="field">
            <span>Exclude patterns</span>
            <textarea v-model="excludeText" class="control textarea" rows="8" />
          </label>
        </div>
      </section>
    </div>

    <section v-if="loading || error || result" class="result-panel">
      <div class="panel-head">
        <h2>生成结果</h2>
        <span v-if="loading" class="status running">Running</span>
        <span v-else-if="error" class="status failed">Failed</span>
        <span v-else class="status success">Success</span>
      </div>

      <div v-if="loading" class="loading-state">
        正在分析代码结构并生成章节，工具调用期间可能短暂停顿。
      </div>
      <div v-else-if="error" class="error-state">
        {{ error }}
      </div>
      <div v-else-if="result" class="result-body">
        <div class="output-row">
          <div>
            <span class="muted">Output</span>
            <code>{{ result.output_dir }}</code>
          </div>
          <button type="button" class="ghost-btn" @click="copyText('路径', result.output_dir)">
            {{ copied === '路径' ? '已复制' : '复制路径' }}
          </button>
        </div>

        <div class="file-head">
          <span>{{ result.project_name }}</span>
          <button
            type="button"
            class="ghost-btn"
            @click="copyText('文件', result.files.map(file => file.path).join('\n'))"
          >
            {{ copied === '文件' ? '已复制' : '复制文件清单' }}
          </button>
        </div>
        <ul class="file-list">
          <li v-for="file in result.files" :key="file.path">
            <span>{{ file.path }}</span>
            <small>{{ formatSize(file.size) }}</small>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.wiki-page {
  height: 100%;
  overflow-y: auto;
  padding: 1.25rem;
}

.hero {
  width: min(1120px, 100%);
  margin: 0 auto 1rem;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.eyebrow {
  margin: 0 0 0.35rem;
  color: #74d6bd;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 2rem;
  line-height: 1.15;
}

h2 {
  font-size: 1rem;
}

.content-grid {
  width: min(1120px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.4fr);
  gap: 1rem;
}

.source-panel,
.params-panel,
.result-panel {
  background: rgba(20, 18, 30, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.75rem;
  padding: 1rem;
}

.result-panel {
  width: min(1120px, 100%);
  margin: 1rem auto 0;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.segmented {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  padding: 0.18rem;
  border-radius: 0.6rem;
  background: rgba(255, 255, 255, 0.06);
}

.segment {
  min-width: 4.5rem;
  padding: 0.38rem 0.7rem;
  border-radius: 0.45rem;
  background: transparent;
  color: rgba(232, 230, 240, 0.72);
}

.segment.active {
  background: #ececf5;
  color: #171421;
}

.field-stack,
.form-grid,
.pattern-grid {
  display: grid;
  gap: 0.85rem;
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.pattern-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 0.95rem;
}

.field {
  display: grid;
  gap: 0.4rem;
  color: rgba(232, 230, 240, 0.66);
  font-size: 0.78rem;
}

.control {
  width: 100%;
  min-height: 2.5rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 0.55rem;
  padding: 0.55rem 0.65rem;
  color: #ececf5;
  font: inherit;
}

.control:focus {
  outline: none;
  border-color: rgba(116, 214, 189, 0.65);
}

.textarea {
  min-height: 12rem;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.5;
}

.check-field {
  min-height: 2.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: rgba(232, 230, 240, 0.78);
  font-size: 0.86rem;
}

.drop-zone {
  min-height: 5rem;
  display: grid;
  place-items: center;
  padding: 0.85rem;
  border: 1px dashed rgba(116, 214, 189, 0.38);
  border-radius: 0.65rem;
  color: rgba(232, 230, 240, 0.58);
  text-align: center;
  font-size: 0.85rem;
}

.primary-btn,
.ghost-btn {
  min-height: 2.4rem;
  border-radius: 0.55rem;
  padding: 0.55rem 0.9rem;
  color: #fff;
}

.primary-btn {
  background: #319f86;
  font-weight: 700;
}

.primary-btn:disabled {
  opacity: 0.42;
}

.ghost-btn {
  background: rgba(255, 255, 255, 0.07);
  color: #ececf5;
  white-space: nowrap;
}

.status {
  border-radius: 999px;
  padding: 0.25rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 700;
}

.status.running {
  background: rgba(85, 166, 255, 0.16);
  color: #91c6ff;
}

.status.failed {
  background: rgba(255, 107, 107, 0.16);
  color: #ff9a9a;
}

.status.success {
  background: rgba(116, 214, 189, 0.16);
  color: #8ee8d3;
}

.loading-state,
.error-state {
  font-size: 0.9rem;
  line-height: 1.6;
}

.error-state {
  color: #ff9a9a;
}

.result-body {
  display: grid;
  gap: 1rem;
}

.output-row,
.file-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.muted {
  display: block;
  margin-bottom: 0.25rem;
  color: rgba(232, 230, 240, 0.5);
  font-size: 0.72rem;
}

code {
  word-break: break-all;
  color: #f1f1f8;
}

.file-head {
  color: rgba(232, 230, 240, 0.8);
  font-weight: 700;
}

.file-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.4rem;
}

.file-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 2.15rem;
  padding: 0.45rem 0.6rem;
  border-radius: 0.45rem;
  background: rgba(255, 255, 255, 0.045);
}

.file-list span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.file-list small {
  color: rgba(232, 230, 240, 0.5);
  white-space: nowrap;
}

@media (max-width: 860px) {
  .wiki-page {
    padding: 1rem 0.75rem;
  }

  .hero,
  .content-grid,
  .result-panel {
    width: 100%;
  }

  .hero,
  .content-grid,
  .form-grid,
  .pattern-grid,
  .output-row,
  .file-head {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }

  h1 {
    font-size: 1.55rem;
  }
}
</style>
