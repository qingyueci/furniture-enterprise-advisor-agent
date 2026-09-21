<script setup lang="ts">
import type { ProductComparisonData } from '../api/agent'
import PriceResult from './PriceResult.vue'

defineProps<{ data: ProductComparisonData }>()
function stateClass(status: string) { return status === 'AVAILABLE' || status === 'SUCCESS' ? 'success' : status === 'PARTIAL' || status === 'CONFLICT' ? 'warning' : 'error' }
function budgetLabel(value: boolean | null) { return value === true ? '预算内' : value === false ? '超出预算' : '暂不能判断' }
</script>

<template>
  <section class="comparison" aria-label="产品结构化比较">
    <div class="comparison-title"><div><span>结构化比较</span><h3>{{ data.products[0] }} / {{ data.products[1] }}</h3></div><span :class="['state', stateClass(data.overall_status)]">{{ data.overall_status }}</span></div>
    <div v-if="data.summaries.length" class="summary-grid">
      <article v-for="summary in data.summaries" :key="summary.product_name"><b>{{ summary.product_name }}</b><p>{{ summary.summary ?? '资料未提供' }}</p></article>
    </div>
    <PriceResult :cards="data.price_cards" />
    <div v-if="data.rows.length" class="comparison-table-wrap">
      <table class="comparison-table"><thead><tr><th>比较维度</th><th>{{ data.products[0] }}</th><th>{{ data.products[1] }}</th><th>状态</th></tr></thead><tbody><tr v-for="row in data.rows" :key="row.dimension"><th>{{ row.dimension }}</th><td>{{ row.values[0] || '资料未提供' }}</td><td>{{ row.values[1] || '资料未提供' }}</td><td><span :class="['state', stateClass(row.status)]">{{ row.status }}</span><small v-if="row.note">{{ row.note }}</small></td></tr></tbody></table>
    </div>
    <section v-if="data.budget_check" class="report-section"><h4>预算判断 <span class="numeric">{{ data.budget_check.budget }} {{ data.budget_check.currency }}</span></h4><div class="budget-grid"><article v-for="(product, index) in data.products" :key="product"><b>{{ product }}</b><span :class="['state', data.budget_check.within_budget[index] === true ? 'success' : data.budget_check.within_budget[index] === false ? 'error' : 'warning']">{{ budgetLabel(data.budget_check.within_budget[index]) }}</span><p>{{ data.budget_check.reasons[index] }}</p></article></div></section>
    <section class="report-section"><h4>条件式推荐</h4><div v-if="data.recommendation" class="recommendation"><b>{{ data.recommendation.recommended_product ?? '不强选产品' }}</b><p>{{ data.recommendation.condition }}</p><p v-if="data.recommendation.rationale">{{ data.recommendation.rationale }}</p></div><p v-else class="muted">当前证据不足，不强选产品。</p></section>
    <div class="claim-grid">
      <section class="report-section"><h4>优势</h4><template v-for="product in data.products" :key="product"><b>{{ product }}</b><ul><li v-for="claim in data.advantages[product] ?? []" :key="claim.text">{{ claim.text }}</li><li v-if="!(data.advantages[product]?.length)" class="muted">资料未提供</li></ul></template></section>
      <section class="report-section"><h4>不足</h4><template v-for="product in data.products" :key="product"><b>{{ product }}</b><ul><li v-for="claim in data.limitations[product] ?? []" :key="claim.text">{{ claim.text }}</li><li v-if="!(data.limitations[product]?.length)" class="muted">资料未提供</li></ul></template></section>
    </div>
    <section v-if="data.missing_fields.length" class="report-section missing"><h4>缺失与冲突</h4><article v-for="item in data.missing_fields" :key="`${item.field}-${item.message}`"><span :class="['state', stateClass(item.status)]">{{ item.status }}</span><b>{{ item.field }}</b><p>{{ item.message || '资料未提供' }}</p></article></section>
  </section>
</template>

<style scoped>
.comparison { margin-top: 14px; }
.comparison-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-top: 14px; border-top: 1px solid var(--color-border); }
.comparison-title span:first-child { color: var(--color-accent); font-size: 10px; font-weight: 700; letter-spacing: .8px; }
.comparison-title h3 { margin: 5px 0 0; font-size: 16px; }
.summary-grid, .budget-grid, .claim-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.summary-grid article, .budget-grid article { padding: 12px; border-left: 3px solid var(--color-accent); background: var(--color-surface-subtle); }
.summary-grid b, .budget-grid b, .claim-grid b { display: block; margin-bottom: 5px; font-size: 12px; }
.summary-grid p, .budget-grid p, .recommendation p, .report-section li, .missing p { margin: 4px 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.comparison-table-wrap { max-width: 100%; margin-top: 14px; overflow-x: auto; border: 1px solid var(--color-border); border-radius: 9px; }
.comparison-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 11px; }
.comparison-table th, .comparison-table td { padding: 10px; border-right: 1px solid var(--color-border-soft); border-bottom: 1px solid var(--color-border-soft); text-align: left; vertical-align: top; line-height: 1.55; overflow-wrap: anywhere; }
.comparison-table th { background: var(--color-surface-subtle); color: var(--color-text-secondary); }
.comparison-table tr:last-child th, .comparison-table tr:last-child td { border-bottom: 0; }
.comparison-table th:last-child, .comparison-table td:last-child { border-right: 0; }
.comparison-table small { display: block; margin-top: 5px; color: var(--color-text-tertiary); }
.report-section { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--color-border-soft); }
.report-section h4 { display: flex; justify-content: space-between; margin: 0 0 9px; font-size: 13px; }
.recommendation { padding: 12px; border-left: 3px solid var(--color-accent); background: var(--color-accent-soft); }
.claim-grid .report-section { margin-top: 0; }
.claim-grid ul { margin: 0 0 10px; padding-left: 18px; }
.missing article { display: grid; grid-template-columns: auto 120px minmax(0, 1fr); align-items: start; gap: 8px; padding: 8px 0; }
.missing b { font-size: 12px; }
.missing p { margin: 0; }
</style>
