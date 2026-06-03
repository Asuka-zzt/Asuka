<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInline(text: string): string {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/_([^_]+)_/g, '<em>$1</em>')
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>',
    )
}

function renderList(lines: string[], ordered: boolean): string {
  const items = lines.map((line) => {
    const text = ordered
      ? line.replace(/^\s*\d+[.)]\s+/, '')
      : line.replace(/^\s*[-*]\s+/, '')
    return `<li>${renderInline(text)}</li>`
  })
  return `<${ordered ? 'ol' : 'ul'}>${items.join('')}</${ordered ? 'ol' : 'ul'}>`
}

function renderMarkdown(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index] ?? ''

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trimStart().startsWith('```')) {
      const language = line.trim().slice(3).trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !(lines[index] ?? '').trimStart().startsWith('```')) {
        codeLines.push(lines[index] ?? '')
        index += 1
      }
      if (index < lines.length)
        index += 1
      blocks.push(
        `<pre><code${language ? ` data-language="${escapeHtml(language)}"` : ''}>${escapeHtml(codeLines.join('\n'))}</code></pre>`,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const listLines: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index] ?? '')) {
        listLines.push(lines[index] ?? '')
        index += 1
      }
      blocks.push(renderList(listLines, false))
      continue
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const listLines: string[] = []
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index] ?? '')) {
        listLines.push(lines[index] ?? '')
        index += 1
      }
      blocks.push(renderList(listLines, true))
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index] ?? '')) {
        quoteLines.push((lines[index] ?? '').replace(/^\s*>\s?/, ''))
        index += 1
      }
      blocks.push(`<blockquote>${quoteLines.map(renderInline).join('<br>')}</blockquote>`)
      continue
    }

    if (/^\s*---+\s*$/.test(line)) {
      blocks.push('<hr>')
      index += 1
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (
      index < lines.length
      && (lines[index] ?? '').trim()
      && !/^(#{1,4})\s+/.test(lines[index] ?? '')
      && !/^\s*[-*]\s+/.test(lines[index] ?? '')
      && !/^\s*\d+[.)]\s+/.test(lines[index] ?? '')
      && !/^\s*>\s?/.test(lines[index] ?? '')
      && !(lines[index] ?? '').trimStart().startsWith('```')
    ) {
      paragraph.push(lines[index] ?? '')
      index += 1
    }
    blocks.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`)
  }

  return blocks.join('')
}

const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div class="markdown-text" v-html="html" />
</template>

<style scoped>
.markdown-text {
  word-break: break-word;
  overflow-wrap: anywhere;
}

.markdown-text :deep(p),
.markdown-text :deep(ul),
.markdown-text :deep(ol),
.markdown-text :deep(blockquote),
.markdown-text :deep(pre) {
  margin: 0.35rem 0;
}

.markdown-text :deep(p:first-child),
.markdown-text :deep(ul:first-child),
.markdown-text :deep(ol:first-child),
.markdown-text :deep(blockquote:first-child),
.markdown-text :deep(pre:first-child) {
  margin-top: 0;
}

.markdown-text :deep(p:last-child),
.markdown-text :deep(ul:last-child),
.markdown-text :deep(ol:last-child),
.markdown-text :deep(blockquote:last-child),
.markdown-text :deep(pre:last-child) {
  margin-bottom: 0;
}

.markdown-text :deep(h1),
.markdown-text :deep(h2),
.markdown-text :deep(h3),
.markdown-text :deep(h4) {
  margin: 0.5rem 0 0.3rem;
  font-size: 0.98rem;
  line-height: 1.35;
}

.markdown-text :deep(ul),
.markdown-text :deep(ol) {
  padding-left: 1.25rem;
}

.markdown-text :deep(blockquote) {
  padding-left: 0.65rem;
  border-left: 3px solid var(--border-strong);
  color: var(--text-muted);
}

.markdown-text :deep(code) {
  padding: 0.08rem 0.25rem;
  border-radius: 0.3rem;
  background: var(--surface-3);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.86em;
}

.markdown-text :deep(pre) {
  overflow-x: auto;
  padding: 0.65rem;
  border: 1px solid var(--border);
  border-radius: 0.45rem;
  background: var(--surface-3);
}

.markdown-text :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-text :deep(a) {
  color: var(--primary-strong);
  text-decoration: underline;
}

.markdown-text :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 0.65rem 0;
}
</style>
