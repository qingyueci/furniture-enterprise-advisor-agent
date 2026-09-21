<script setup lang="ts">
import type { ToolCallSummary } from '../api/agent'

defineProps<{ tools: ToolCallSummary[] }>()
const labels: Record<string, string> = {
  search_product_knowledge: '检索产品资料', read_document: '读取文档', query_product_price: '查询结构化价格', compare_products: '聚合产品比较',
}
function stateClass(status: ToolCallSummary['status']) {
  return status === 'SUCCESS' ? 'success' : status === 'PARTIAL' ? 'warning' : 'error'
}
</script>

<template>
  <section class="tool-section" aria-label="工具调用记录">
    <div class="section-label"><span>工具记录</span><b>{{ tools.length }}</b></div>
    <div v-if="tools.length" class="tool-list">
      <article v-for="(item, index) in tools" :key="`${item.tool}-${index}`">
        <div><strong>{{ labels[item.tool] ?? item.tool }}</strong><code>{{ item.tool }}</code></div>
        <div class="tool-outcome"><span :class="['state', stateClass(item.status)]">{{ item.status }}</span><small class="numeric">{{ item.duration_ms }} ms</small></div>
      </article>
    </div>
    <div v-else class="mini-empty">本条回答没有工具记录。</div>
  </section>
</template>

<style scoped>
.section-label { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 10px; color: var(--color-text-secondary); font-size: 11px; font-weight: 700; letter-spacing: .8px; }
.section-label b { font-variant-numeric: tabular-nums; }
.tool-list { display: grid; gap: 7px; }
.tool-list article { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 10px; border: 1px solid var(--color-border-soft); border-radius: 9px; background: var(--color-surface); }
.tool-list strong, .tool-list code { display: block; }
.tool-list strong { font-size: 11px; }
.tool-list code { margin-top: 3px; color: var(--color-text-tertiary); font-size: 9px; overflow-wrap: anywhere; }
.tool-outcome { display: grid; justify-items: end; gap: 3px; }
.tool-outcome small { color: var(--color-text-tertiary); font-size: 10px; }
.mini-empty { padding: 16px; color: var(--color-text-tertiary); text-align: center; font-size: 11px; }
</style>
