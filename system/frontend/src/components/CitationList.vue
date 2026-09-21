<script setup lang="ts">
import type { Citation } from '../api/agent'

const props = defineProps<{ citations: Citation[]; messageId?: string | null; highlightedRef?: string | null }>()

// Excel 记录的字段在历史索引中以“；”或空白串联保存。展示层按字段名
// 重新断行，既兼容旧索引，也不改变引用原文和来源元数据。
const FIELD_LABELS = [
  '不适用/限制条件', '基材/材质', '饰面/工艺', '标准名称', '别名/俗称',
  '产品状态', '适用空间', '实体类型', '环保等级', '有效开始', '有效结束',
  '证据类型', '来源说明', '原记录', '内容URL', '内容ID', '实体ID', '来源ID',
  '记录ID', '工作表', '行号', '品牌', '系列', '型号', '厚度(mm)', '宽度(mm)',
  '高度(mm)', '深度(mm)', '来源', '备注', '置信度', '报价规格', '计价单位',
  '包含范围',
]
const FIELD_BOUNDARY = FIELD_LABELS.map(label => label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
const NEXT_FIELD = new RegExp(`(?:(?:[；;])|[\\t\\u00a0 ]+)[\\t\\u00a0 ]*(?=(?:${FIELD_BOUNDARY})[：:])`, 'g')

const SOURCE_TYPE_LABELS: Record<string, string> = {
  DOCUMENT: '文档资料', PRICE: '结构化价格', PRODUCT: '产品资料',
}
const EVIDENCE_LABELS: Record<string, string> = {
  PRODUCT_FACT: '产品事实', OFFICIAL_SOURCE: '官方来源', PRODUCT_RELATION: '产品关系',
  SELECTION_GUIDE: '选型参考', PLATFORM_STATEMENT: '平台观点', USER_PAIN_POINT: '用户痛点',
  SUPPLIER_QUOTE: '供应商报价', SOURCE_REGISTRY: '来源登记', CHANGE_EVENT: '变化事件',
}

function formatQuote(value: string | null) {
  if (!value) return ''
  return value
    .replace(/\r\n?/g, '\n')
    .replace(NEXT_FIELD, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function location(item: Citation) {
  const parts: string[] = []
  if (item.page_start) parts.push(item.page_end && item.page_end !== item.page_start ? `第 ${item.page_start}–${item.page_end} 页` : `第 ${item.page_start} 页`)
  if (item.worksheet || item.section_title) parts.push(`工作表：${item.worksheet || item.section_title}`)
  if (item.row_start) parts.push(item.row_end && item.row_end !== item.row_start ? `第 ${item.row_start}–${item.row_end} 行` : `第 ${item.row_start} 行`)
  return parts.join(' · ')
}

function sourceLabel(value: string) {
  return SOURCE_TYPE_LABELS[value] ?? '资料引用'
}

function evidenceLabel(value: string | null) {
  return value ? (EVIDENCE_LABELS[value] ?? '其他资料') : '其他资料'
}

function excerpt(value: string | null, limit = 260) {
  const text = formatQuote(value)
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function cardKey(item: Citation, index: number) {
  return `${props.messageId ?? 'message'}-${item.ref ?? index + 1}`
}
</script>

<template>
  <section class="evidence-block" aria-label="引用证据">
    <div class="section-label"><span>引用</span><b>{{ citations.length }}</b></div>
    <div v-if="citations.length" class="citation-list">
      <article v-for="(item, index) in citations" :id="`citation-card-${cardKey(item, index)}`" :key="`${item.source_type}-${item.ref ?? index}`" :class="['citation-item', { highlighted: highlightedRef === (item.ref ?? String(index + 1)) }]">
        <div class="citation-index">{{ item.ref ?? index + 1 }}</div>
        <div>
          <span class="state accent">{{ sourceLabel(item.source_type) }}</span>
          <span class="state">{{ evidenceLabel(item.evidence_category) }}</span>
          <h4 v-if="item.source_type === 'DOCUMENT'">{{ item.document_name ?? '文档资料' }}</h4>
          <h4 v-else>{{ item.source ?? '结构化数据源' }}</h4>
          <p v-if="item.quote">{{ excerpt(item.quote) }}</p>
          <details v-if="item.quote && formatQuote(item.quote).length > 260" class="citation-details">
            <summary>展开完整摘录</summary>
            <p class="full-quote">{{ formatQuote(item.quote) }}</p>
          </details>
          <small v-if="location(item)">{{ location(item) }}</small>
          <small v-if="item.record_id || item.source_id" class="mono">记录：{{ item.record_id ?? '—' }} · 来源：{{ item.source_id ?? '—' }}</small>
          <small v-if="item.usage_restriction">使用限制：{{ item.usage_restriction }}</small>
          <small v-if="item.source_type === 'PRICE'" class="mono">price_id: {{ item.price_id ?? '—' }} · product_id: {{ item.product_id ?? '—' }}</small>
        </div>
      </article>
    </div>
    <div v-else class="mini-empty">本条回答没有返回引用。</div>
  </section>
</template>

<style scoped>
.section-label { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; color: var(--color-text-secondary); font-size: 11px; font-weight: 700; letter-spacing: .8px; }
.section-label b { font-variant-numeric: tabular-nums; }
.citation-list { display: grid; gap: 8px; }
.citation-item { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 9px; padding: 10px; border: 1px solid var(--color-border-soft); border-radius: 9px; background: var(--color-surface); }
.citation-item.highlighted { border-color: var(--color-accent); box-shadow: 0 0 0 2px var(--color-accent-soft); }
.citation-index { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; background: var(--color-accent-soft); color: var(--color-accent); font-size: 11px; font-weight: 800; }
h4 { margin: 6px 0 3px; overflow-wrap: anywhere; font-size: 12px; }
p { margin: 0 0 6px; color: var(--color-text-secondary); font-size: 11px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.citation-details { margin: 4px 0 7px; color: var(--color-accent); font-size: 10px; }
.citation-details summary { cursor: pointer; }
.citation-details .full-quote { margin-top: 5px; color: var(--color-text-secondary); }
small { display: block; color: var(--color-text-tertiary); font-size: 10px; line-height: 1.5; overflow-wrap: anywhere; }
.mini-empty { padding: 16px; color: var(--color-text-tertiary); text-align: center; font-size: 11px; }
</style>
