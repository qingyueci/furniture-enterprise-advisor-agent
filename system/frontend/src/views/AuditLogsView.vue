<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { fetchAuditLogs, type AuditAction, type AuditLogListData, type AuditResourceType, type AuditResult } from '../api/audit'
import { messageFor } from '../api/http'

const data = ref<AuditLogListData>({ items: [], pagination: { page: 1, page_size: 20, total: 0 } })
const loading = ref(false)
const error = ref('')
const expandedId = ref<string | number | null>(null)
const filters = reactive<{ username: string; action: AuditAction | ''; resourceType: AuditResourceType | ''; result: AuditResult | ''; startTime: string; endTime: string; page: number }>({ username: '', action: '', resourceType: '', result: '', startTime: '', endTime: '', page: 1 })
const actions: AuditAction[] = ['LOGIN_SUCCESS','LOGIN_FAILED','LOGOUT','USER_CREATE','USER_UPDATE','DOCUMENT_UPLOAD','DOCUMENT_PARSE_SUCCESS','DOCUMENT_PARSE_FAILED','DOCUMENT_PERMISSION_UPDATE','DOCUMENT_DELETE','DOCUMENT_READ','PRODUCT_QUERY','PRICE_QUERY','AGENT_CHAT','AGENT_TOOL_CALL','PERMISSION_DENIED']
const resourceTypes: AuditResourceType[] = ['AUTH','USER','DOCUMENT','PRODUCT','PRICE','AGENT']
const results: AuditResult[] = ['SUCCESS','FAILED','DENIED']

function iso(value: string) { return value ? new Date(value).toISOString() : undefined }
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
function resultClass(value: AuditResult) { return value === 'SUCCESS' ? 'success' : 'error' }
async function load(page = filters.page) {
  loading.value = true; error.value = ''; filters.page = page
  try { data.value = await fetchAuditLogs({ username: filters.username || undefined, action: filters.action || undefined, resource_type: filters.resourceType || undefined, result: filters.result || undefined, start_time: iso(filters.startTime), end_time: iso(filters.endTime), page, page_size: 20 }) }
  catch (exception) { error.value = messageFor(exception, '审计日志加载失败。') }
  finally { loading.value = false }
}
function reset() { filters.username = ''; filters.action = ''; filters.resourceType = ''; filters.result = ''; filters.startTime = ''; filters.endTime = ''; void load(1) }
onMounted(() => load(1))
</script>

<template>
  <section class="page audit-page">
    <header class="page-heading management-heading"><div><span class="kicker">ADMIN · TRACE LEDGER</span><h1>审计日志</h1><p>只读查询认证、资料、产品、价格与 Agent 工具行为；备注保持后端脱敏结果。</p></div><span class="state accent">READ ONLY</span></header>
    <form class="filter-bar panel" @submit.prevent="load(1)">
      <label class="filter-field grow">用户名<input v-model="filters.username" maxlength="64" placeholder="精确或模糊用户名" /></label>
      <label class="filter-field">动作<select v-model="filters.action"><option value="">全部动作</option><option v-for="item in actions" :key="item" :value="item">{{ item }}</option></select></label>
      <label class="filter-field">资源类型<select v-model="filters.resourceType"><option value="">全部资源</option><option v-for="item in resourceTypes" :key="item" :value="item">{{ item }}</option></select></label>
      <label class="filter-field">结果<select v-model="filters.result"><option value="">全部结果</option><option v-for="item in results" :key="item" :value="item">{{ item }}</option></select></label>
      <label class="filter-field">开始时间<input v-model="filters.startTime" type="datetime-local" /></label>
      <label class="filter-field">结束时间<input v-model="filters.endTime" type="datetime-local" /></label>
      <div class="actions"><button class="button primary" :disabled="loading">查询</button><button class="button" type="button" :disabled="loading" @click="reset">重置</button></div>
    </form>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <div class="table-wrap audit-table-wrap" :aria-busy="loading">
      <div v-if="loading" class="loading-state">正在加载审计日志…</div>
      <div v-else-if="!data.items.length" class="empty-state">当前条件下没有审计记录。</div>
      <table v-else class="data-table audit-table"><thead><tr><th>时间</th><th>用户</th><th>动作 / 资源</th><th>结果</th><th>详情</th></tr></thead><tbody><template v-for="item in data.items" :key="item.id"><tr><td class="numeric">{{ formatDate(item.created_at) }}</td><td>{{ item.username ?? '匿名' }}</td><td><strong>{{ item.action }}</strong><small>{{ item.resource_type ?? '—' }} · {{ item.resource_id ?? '—' }}</small></td><td><span :class="['state', resultClass(item.result)]">{{ item.result }}</span></td><td><button class="detail-toggle" type="button" :aria-expanded="expandedId === item.id" @click="expandedId = expandedId === item.id ? null : item.id">{{ expandedId === item.id ? '收起' : '展开' }}</button></td></tr><tr v-if="expandedId === item.id" class="audit-detail-row"><td colspan="5"><dl><div><dt>请求编号</dt><dd class="mono">{{ item.detail.request_id ?? '—' }}</dd></div><div><dt>IP</dt><dd class="mono">{{ item.request_ip ?? '—' }}</dd></div><div><dt>工具</dt><dd class="mono">{{ item.detail.tool ?? '—' }}</dd></div><div><dt>耗时</dt><dd class="numeric">{{ item.detail.duration_ms === null ? '—' : item.detail.duration_ms + ' ms' }}</dd></div><div><dt>错误代码</dt><dd class="mono">{{ item.detail.error_code ?? '—' }}</dd></div><div><dt>备注</dt><dd>{{ item.detail.note ?? '—' }}</dd></div></dl></td></tr></template></tbody></table>
    </div>
    <footer class="pagination"><span>共 <b class="numeric">{{ data.pagination.total }}</b> 条 · 第 {{ data.pagination.page }} 页</span><div class="pagination-actions"><button class="button" :disabled="loading || filters.page <= 1" @click="load(filters.page - 1)">上一页</button><button class="button" :disabled="loading || filters.page * data.pagination.page_size >= data.pagination.total" @click="load(filters.page + 1)">下一页</button></div></footer>
  </section>
</template>

<style scoped>
.audit-table-wrap { max-height: calc(100vh - 310px); }
.audit-table { min-width: 760px; }
.audit-table td { max-width: 210px; overflow-wrap: anywhere; }
.audit-table td:first-child { min-width: 150px; }
.audit-table strong, .audit-table small { display: block; }
.audit-table strong { font-size: 11px; }
.audit-table small { margin-top: 4px; color: var(--color-text-tertiary); font-size: 10px; line-height: 1.45; }
.detail-toggle { border: 0; background: transparent; color: var(--color-text-primary); cursor: pointer; font: inherit; text-decoration: underline; text-underline-offset: 4px; }
.audit-detail-row td { padding: 0; background: var(--color-surface-subtle); }
.audit-detail-row dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 24px; margin: 0; padding: 18px 24px; }
.audit-detail-row dl div { min-width: 0; }
.audit-detail-row dt { margin-bottom: 4px; color: var(--color-text-tertiary); font-size: 10px; }
.audit-detail-row dd { margin: 0; overflow-wrap: anywhere; font-size: 11px; }
@media (max-width: 800px) { .audit-detail-row dl { grid-template-columns: 1fr 1fr; } }
</style>
