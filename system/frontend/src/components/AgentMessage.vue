<script setup lang="ts">
import { computed } from 'vue'
import type { ConversationMessage } from '../api/agent'
import PriceResult from './PriceResult.vue'
import ProductComparison from './ProductComparison.vue'

const props = defineProps<{ message: ConversationMessage; selected?: boolean }>()
const emit = defineEmits<{ (event: 'citation-select', ref: string): void }>()

function escapeHtml(value: string) {
  // Older responses were persisted with escaped angle brackets; normalize those
  // entities before applying the safe renderer so history remains readable.
  const legacy = value.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
  return legacy.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function inline(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([0-9]+)\]/g, '<button type="button" class="citation-mark" data-citation-ref="$1" aria-label="查看引用 $1">[$1]</button>')
}

function renderMarkdown(value: string) {
  const lines = value.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const table = line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])
    if (table) {
      closeList()
      const cells = (text: string) => text.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => `<td>${inline(cell.trim())}</td>`).join('')
      out.push(`<div class="md-table-wrap"><table><tbody><tr>${cells(line).replace(/<td>/g, '<th>').replace(/<\/td>/g, '</th>')}</tr>`)
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) { out.push(`<tr>${cells(lines[i])}</tr>`); i += 1 }
      out.push('</tbody></table></div>')
      i -= 1
      continue
    }
    const heading = line.match(/^\s{0,3}(#{1,3})\s+(.+)$/)
    if (heading) { closeList(); out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`); continue }
    const bullet = line.match(/^\s*[-*]\s+(.+)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (bullet || numbered) {
      const kind = bullet ? 'ul' : 'ol'
      if (list !== kind) { closeList(); list = kind; out.push(`<${kind}>`) }
      out.push(`<li>${inline((bullet ?? numbered)![1])}</li>`)
      continue
    }
    closeList()
    if (!line.trim()) continue
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  return out.join('') || '<p></p>'
}

const renderedContent = computed(() => props.message.role === 'ASSISTANT' ? renderMarkdown(props.message.content) : '')
const taskLabel: Record<string, string> = {
  CONSULTATION: '资料咨询', PRICE_QUERY: '价格结果', PRODUCT_COMPARE: '产品比较',
  PRODUCT_RECOMMENDATION: '产品建议', KNOWLEDGE_QUERY: '资料问答', DOCUMENT_READ: '文档摘录',
}

// 稳定警告代码到可见中文的固定映射；未知代码统一兜底，不展示内部原因码。
const warningText: Record<string, string> = {
  ROUTING_FALLBACK: '本轮采用确定性路由，请结合回答与引用核验',
  GENERATION_FALLBACK: '本轮生成已降级为受控结果，请优先核验引用',
  PERMISSION_SCOPE_LIMITED: '当前回答受资料权限范围限制',
  EVIDENCE_FILTERED_OUT: '候选证据经范围校验后未被采用',
  NO_EVIDENCE_FALLBACK: '当前授权范围内未找到可用证据',
  TOOL_EXECUTION_FAILED: '部分工具执行失败，结果可能不完整',
  PARTIAL_RESULT: '当前仅返回部分结果',
  DOCUMENT_TRUNCATED: '文档内容已按读取上限截取',
}
const defaultWarningText = '本轮存在状态提醒，请核验回答和引用'

const warningCodes = computed(() => props.message.role === 'ASSISTANT'
  ? [...new Set(props.message.warnings ?? [])].filter(code => typeof code === 'string' && code)
  : [])
const warningItems = computed(() => warningCodes.value.map(code => ({ code, text: warningText[code] ?? defaultWarningText })))
// 与警告区域同义的旧降级标记不再重复展示，由警告区域统一承担。
const showDegradedBadge = computed(() => props.message.structured_data?.kind === 'CONSULTATION'
  && props.message.structured_data.degraded
  && !warningCodes.value.includes('GENERATION_FALLBACK'))

function handleContentClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest<HTMLElement>('[data-citation-ref]')
  if (target?.dataset.citationRef) emit('citation-select', target.dataset.citationRef)
}
</script>

<template>
  <article :class="['message', message.role.toLowerCase(), { selected }]">
    <div class="message-meta"><span>{{ message.role === 'USER' ? '问题' : 'Agent 结果' }}</span><time>{{ new Date(message.created_at).toLocaleString('zh-CN', { hour12: false }) }}</time></div>
    <div v-if="message.role === 'USER'" class="message-content user-content">{{ message.content }}</div>
    <div v-else class="message-content assistant-content" v-html="renderedContent" @click="handleContentClick" />
    <PriceResult v-if="message.structured_data?.kind === 'PRICE_QUERY'" :cards="message.structured_data.price_cards" />
    <ProductComparison v-if="message.structured_data?.kind === 'PRODUCT_COMPARISON'" :data="message.structured_data" />
    <div v-if="warningItems.length" class="message-warnings" role="status">
      <p v-for="item in warningItems" :key="item.code" class="message-warning">{{ item.text }}</p>
    </div>
    <div v-if="message.role === 'ASSISTANT'" class="message-foot"><span><span v-if="message.task_type" class="state accent">{{ taskLabel[message.task_type] ?? '资料回答' }}</span><span v-if="showDegradedBadge" class="state warning">已降级 · 请核验摘录</span></span><span class="muted">{{ message.citations.length }} 条引用 · {{ message.tool_summary.length }} 次工具调用</span></div>
  </article>
</template>

<style scoped>
.message { width: min(100%, 900px); padding: 15px 16px; border: 1px solid var(--color-border); border-radius: 11px; background: var(--color-surface); }
.message.user { width: min(78%, 720px); margin-left: auto; border-color: var(--color-accent); background: var(--color-accent-soft); }
.message.selected { box-shadow: inset 3px 0 0 var(--color-accent); }
.message-meta { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; color: var(--color-text-tertiary); font-size: 10px; }
.message-meta span { color: var(--color-accent); font-weight: 700; letter-spacing: .8px; }
.message-content { color: var(--color-text-primary); font-size: 13px; line-height: 1.75; overflow-wrap: anywhere; }
.user-content { white-space: pre-wrap; }
.assistant-content :deep(p) { margin: 0 0 9px; }
.assistant-content :deep(p:last-child) { margin-bottom: 0; }
.assistant-content :deep(h1), .assistant-content :deep(h2), .assistant-content :deep(h3) { margin: 13px 0 7px; line-height: 1.35; }
.assistant-content :deep(h1) { font-size: 18px; }.assistant-content :deep(h2) { font-size: 16px; }.assistant-content :deep(h3) { font-size: 14px; }
.assistant-content :deep(ul), .assistant-content :deep(ol) { margin: 6px 0 10px; padding-left: 22px; }
.assistant-content :deep(li) { margin: 3px 0; }
.assistant-content :deep(code) { padding: 1px 4px; border-radius: 4px; background: var(--color-surface-inset); font-family: ui-monospace, monospace; font-size: .9em; }
.assistant-content :deep(.citation-mark) { margin: 0 1px; padding: 0; border: 0; background: transparent; color: var(--color-accent); cursor: pointer; font-size: .8em; font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }
.assistant-content :deep(.citation-mark:focus-visible) { outline: 2px solid var(--color-accent); outline-offset: 2px; border-radius: 3px; }
.md-table-wrap { max-width: 100%; margin: 9px 0 12px; overflow-x: auto; }
.assistant-content :deep(table) { min-width: 420px; border-collapse: collapse; font-size: 12px; }
.assistant-content :deep(th), .assistant-content :deep(td) { padding: 7px 9px; border: 1px solid var(--color-border-soft); text-align: left; vertical-align: top; }
.assistant-content :deep(th) { background: var(--color-surface-subtle); font-weight: 700; }
.message-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--color-border-soft); font-size: 10px; }
.message-warnings { display: grid; gap: 4px; margin-top: 11px; padding: 8px 10px; border: 1px solid var(--color-border-soft); border-left: 3px solid var(--color-warning, #b45309); border-radius: 7px; background: var(--color-warning-soft, #fef3c7); }
.message-warning { margin: 0; color: var(--color-text-secondary); font-size: 10px; line-height: 1.55; }
</style>
