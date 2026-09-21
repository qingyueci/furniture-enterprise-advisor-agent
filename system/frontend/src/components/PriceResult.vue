<script setup lang="ts">
import type { PriceCard } from '../api/agent'

defineProps<{ cards: PriceCard[] }>()
function statusClass(status: PriceCard['status']) { return status === 'AVAILABLE' ? 'success' : status === 'CONFLICT' ? 'warning' : '' }
function dateLabel(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' }
</script>

<template>
  <section v-if="cards.length" class="price-grid" aria-label="价格结果">
    <article v-for="card in cards" :key="`${card.product_id}-${card.price_type}`" class="price-card">
      <div class="price-head"><span>结构化价格</span><span :class="['state', statusClass(card.status)]">{{ card.status }}</span></div>
      <h3>{{ card.product_name }}</h3>
      <p class="price numeric">{{ card.price ?? '暂无价格' }} <small v-if="card.price">{{ card.currency }}/{{ card.pricing_unit ?? '单位未提供' }}</small></p>
      <dl>
        <div><dt>报价规格</dt><dd>{{ card.quote_spec ?? '资料未提供' }}</dd></div>
        <div><dt>包含范围</dt><dd>{{ card.included_scope ?? '资料未提供' }}</dd></div>
        <div><dt>价格类型</dt><dd>{{ card.price_type }}</dd></div>
        <div><dt>数据来源</dt><dd>{{ card.source ?? '—' }}</dd></div>
        <div><dt>更新时间</dt><dd class="numeric">{{ dateLabel(card.update_time) }}</dd></div>
      </dl>
    </article>
  </section>
</template>

<style scoped>
.price-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.price-card { min-width: 0; padding: 14px; border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface-subtle); }
.price-head { display: flex; justify-content: space-between; align-items: center; color: var(--color-accent); font-size: 10px; font-weight: 700; letter-spacing: .8px; }
h3 { margin: 10px 0 4px; overflow-wrap: anywhere; font-size: 14px; }
.price { margin: 0 0 12px; font-size: 22px; font-weight: 750; }
.price small { color: var(--color-text-secondary); font-size: 11px; font-weight: 600; }
dl { display: grid; gap: 6px; margin: 0; }
dl div { display: grid; grid-template-columns: 66px minmax(0, 1fr); gap: 8px; font-size: 10px; line-height: 1.5; }
dt { color: var(--color-text-tertiary); }
dd { margin: 0; color: var(--color-text-secondary); overflow-wrap: anywhere; }
</style>
