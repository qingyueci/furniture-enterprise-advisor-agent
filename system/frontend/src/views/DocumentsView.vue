<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElDialog, ElMessage, ElPopconfirm, ElTag } from 'element-plus'
import { deleteDocument, downloadDocument, fetchDocuments, updateDocumentPermissions, uploadDocument,
  type DocumentItem, type DocumentListData, type FileType, type ParseStatus, type SecurityLevel } from '../api/documents'
import { fetchProducts, type Product } from '../api/products'
import { messageFor } from '../api/http'
import type { Role } from '../api/auth'

const documents = ref<DocumentListData>({ items: [], pagination: { page: 1, page_size: 20, total: 0 } })
const products = ref<Product[]>([])
const productSearch = ref('')
const productLoading = ref(false)
const productPage = ref(1)
const productTotal = ref(0)
const productCache = ref<Record<number, string>>({})
const loading = ref(false)
const uploading = ref(false)
const uploadOpen = ref(false)
const error = ref('')
const file = ref<File | null>(null)
const fileInputKey = ref(0)
const filters = reactive<{ keyword: string; fileType: FileType | ''; status: ParseStatus | '' }>({ keyword: '', fileType: '', status: '' })
const form = reactive<{ name: string; security: SecurityLevel; roles: Role[]; productIds: number[] }>({
  name: '', security: 'INTERNAL', roles: ['ADMIN', 'PRODUCT_MANAGER'], productIds: [],
})
const editing = ref<DocumentItem | null>(null)
const permissionOpen = computed({ get: () => editing.value !== null, set: value => { if (!value) editing.value = null } })
const permission = reactive<{ security: SecurityLevel; roles: Role[] }>({ security: 'INTERNAL', roles: ['ADMIN'] })
const savingPermission = ref(false)
let pollingTimer: number | null = null
let productRequest = 0
let documentRequest = 0

const productNames = computed(() => new Map(products.value.map(item => [item.id, `${item.product_name} · ${item.model}`])))

function closeUpload() {
  if ((file.value || form.name || form.productIds.length) && !window.confirm('关闭后未提交的资料信息将丢失，确认关闭？')) return
  uploadOpen.value = false
}

function onFile(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  if (file.value && !form.name) form.name = file.value.name.replace(/\.(pdf|docx|xlsx)$/i, '')
}

function syncPolling() {
  const shouldPoll = documents.value.items.some(item => item.parse_status === 'PARSING')
  if (shouldPoll && pollingTimer === null) {
    pollingTimer = window.setInterval(() => { if (!loading.value) void load(true) }, 2000)
  } else if (!shouldPoll && pollingTimer !== null) {
    window.clearInterval(pollingTimer); pollingTimer = null
  }
}

async function load(silent = false) {
  const request = ++documentRequest
  if (!silent) loading.value = true
  error.value = ''
  try {
    const result = await fetchDocuments({ keyword: filters.keyword || undefined, file_type: filters.fileType || undefined,
      parse_status: filters.status || undefined })
    if (request !== documentRequest) return
    documents.value = result
    void ensureProductLabels(result.items)
  } catch (exception) { if (request === documentRequest) error.value = messageFor(exception) }
  finally { if (request === documentRequest) { if (!silent) loading.value = false; syncPolling() } }
}

async function ensureProductLabels(items: DocumentItem[]) {
  const missing = new Set(items.flatMap(item => item.product_ids).filter(id => productCache.value[id] === undefined))
  if (!missing.size) return
  let page = 1
  let total = 0
  try {
    do {
      const result = await fetchProducts({ page, page_size: 100 })
      result.items.forEach(item => {
        productCache.value[item.id] = `${item.product_name} · ${item.model}`
        missing.delete(item.id)
      })
      total = result.pagination.total
      page += 1
    } while (missing.size && (page - 1) * 100 < total)
  } catch {
    // Product labels are an enhancement; the document IDs remain visible when the catalog lookup is unavailable.
  }
}

async function submitUpload() {
  if (!file.value) { error.value = '请选择 PDF、DOCX 或 XLSX 文件。'; return }
  uploading.value = true; error.value = ''
  try {
    await uploadDocument({ file: file.value, document_name: form.name, security_level: form.security,
      allowed_roles: form.roles, product_ids: form.productIds })
    ElMessage.success('资料已安全保存，正在等待知识库处理。')
    file.value = null; form.name = ''; form.security = 'INTERNAL'; form.roles = ['ADMIN', 'PRODUCT_MANAGER']; form.productIds = []
    fileInputKey.value += 1
    uploadOpen.value = false
    await load()
  } catch (exception) { error.value = messageFor(exception) }
  finally { uploading.value = false }
}

async function searchProducts(reset = true) {
  const request = ++productRequest
  const page = reset ? 1 : productPage.value + 1
  productLoading.value = true
  try {
    const result = await fetchProducts({ keyword: productSearch.value.trim() || undefined, page, page_size: 20 })
    if (request !== productRequest) return
    products.value = reset ? result.items : [...products.value, ...result.items.filter(item => !products.value.some(existing => existing.id === item.id))]
    productPage.value = page
    productTotal.value = result.pagination.total
    result.items.forEach(item => { productCache.value[item.id] = `${item.product_name} · ${item.model}` })
  } catch (exception) { if (request === productRequest) error.value = messageFor(exception) }
  finally { if (request === productRequest) productLoading.value = false }
}

function canLoadMoreProducts() { return products.value.length < productTotal.value }

function toggleProduct(id: number) {
  form.productIds = form.productIds.includes(id) ? form.productIds.filter(item => item !== id) : [...form.productIds, id]
}

function selectedProductLabel(id: number) { return productCache.value[id] ?? productNames.value.get(id) ?? `产品 ${id}` }

function beginPermission(item: DocumentItem) {
  editing.value = item
  permission.security = item.security_level
  permission.roles = item.allowed_roles ? [...item.allowed_roles] : ['ADMIN']
}

async function savePermission() {
  if (!editing.value) return
  savingPermission.value = true; error.value = ''
  try {
    await updateDocumentPermissions(editing.value.id, { security_level: permission.security, allowed_roles: permission.roles })
    editing.value = null; ElMessage.success('访问权限已立即更新。'); await load()
  } catch (exception) { error.value = messageFor(exception) }
  finally { savingPermission.value = false }
}

async function download(item: DocumentItem) {
  error.value = ''
  try { await downloadDocument(item); ElMessage.success('下载已开始。') }
  catch (exception) { error.value = messageFor(exception) }
}

async function remove(item: DocumentItem) {
  error.value = ''
  const scrollTop = window.scrollY
  try {
    await deleteDocument(item.id)
    // Keep the list mounted: replacing it with a loading placeholder collapses page height.
    await load(true)
    await nextTick()
    window.scrollTo({ top: Math.min(scrollTop, Math.max(0, document.documentElement.scrollHeight - window.innerHeight)), behavior: 'instant' })
    ElMessage.success('资料已删除。')
  }
  catch (exception) { error.value = messageFor(exception) }
}

function sizeLabel(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function dateLabel(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
function stateLabel(value: ParseStatus) {
  if (value === 'PARSING') return '等待知识库处理'
  if (value === 'READY') return '知识库已就绪'
  if (value === 'FAILED') return '处理失败'
  return '正在上传'
}

onMounted(async () => {
  try { await searchProducts(true) }
  catch (exception) { error.value = messageFor(exception) }
  await load()
})
onUnmounted(() => { if (pollingTimer !== null) window.clearInterval(pollingTimer) })
</script>

<template>
  <section class="page">
    <header class="page-heading management-heading"><div><span class="kicker">ADMIN · DOCUMENT CONTROL</span><h1>产品资料管理</h1><p>安全登记企业资料、关联产品并维护角色访问边界。</p></div><div class="heading-actions"><button class="button primary" type="button" @click="uploadOpen = true">上传新资料</button><div class="limit-note"><b class="numeric">20 MiB</b><span>单文件上限</span><small>PDF · DOCX · XLSX</small></div></div></header>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <div class="document-workspace">
      <div v-if="uploadOpen" class="drawer-backdrop" @click.self="closeUpload">
      <form class="upload-panel panel" role="dialog" aria-modal="true" aria-label="上传新资料" @submit.prevent="submitUpload">
        <button class="drawer-close" type="button" aria-label="关闭上传表单" @click="closeUpload">×</button>
        <div class="panel-title"><span class="step">01</span><div><h2>上传新资料</h2><p>保存后进入知识库处理队列。</p></div></div>
        <label class="drop-zone"><input :key="fileInputKey" type="file" accept=".pdf,.docx,.xlsx" required @change="onFile" /><b>{{ file ? file.name : '选择资料文件' }}</b><small>{{ file ? sizeLabel(file.size) : '仅接受签名匹配的安全文件' }}</small></label>
        <label class="form-field">显示名称<input v-model="form.name" required maxlength="255" placeholder="例如：X100 安装与维护手册" /></label>
        <label class="form-field">安全等级<select v-model="form.security"><option value="PUBLIC">公开</option><option value="INTERNAL">内部</option><option value="RESTRICTED">受限</option></select></label>
        <fieldset><legend>允许角色</legend><label class="check"><input type="checkbox" checked disabled /> 管理员</label><label class="check"><input v-model="form.roles" type="checkbox" value="PRODUCT_MANAGER" /> 产品经理</label><label class="check"><input v-model="form.roles" type="checkbox" value="SALES" /> 销售</label></fieldset>
        <div class="form-field product-picker"><label>关联产品（可选）</label><p class="usage-note">使用说明：选择文件 → 设置名称和访问角色 → 搜索并关联产品 → 上传 → 等待处理完成。关联产品不是必填项。</p><div class="selected-products"><span v-for="id in form.productIds" :key="id" class="selected-product">{{ selectedProductLabel(id) }}<button type="button" :aria-label="`移除关联产品 ${selectedProductLabel(id)}`" @click="toggleProduct(id)">×</button></span><span v-if="!form.productIds.length" class="empty-selection">尚未关联产品</span></div><input v-model="productSearch" placeholder="搜索产品名称、型号或资料编号" maxlength="80" @input="searchProducts(true)" /><div class="product-picker-list"><span v-if="productLoading">正在搜索产品…</span><span v-else-if="!products.length">没有匹配产品</span><template v-else><button v-for="item in products" :key="item.id" type="button" :class="['product-option', { selected: form.productIds.includes(item.id) }]" @click="toggleProduct(item.id)">{{ item.product_name }} · {{ item.model }}</button><button v-if="canLoadMoreProducts()" type="button" class="product-more" :disabled="productLoading" @click="searchProducts(false)">{{ productLoading ? '加载中…' : '加载更多产品' }}</button></template></div></div>
        <button class="button primary" :disabled="uploading">{{ uploading ? '正在安全保存…' : '上传并进入处理队列' }}</button>
      </form>
      </div>
      <section class="ledger panel">
        <div class="panel-header"><div class="panel-title"><span class="step">01</span><div><h2>资料台账</h2><p><b class="numeric">{{ documents.pagination.total }}</b> 份已登记资料</p></div></div><button class="button" :disabled="loading" @click="load()">{{ loading ? '刷新中…' : '刷新' }}</button></div>
        <form class="ledger-filters" @submit.prevent="load()"><label class="filter-field grow">资料名称<input v-model="filters.keyword" maxlength="50" placeholder="按资料名称筛选" /></label><label class="filter-field">文件类型<select v-model="filters.fileType"><option value="">全部类型</option><option value="PDF">PDF</option><option value="DOCX">DOCX</option><option value="XLSX">XLSX</option></select></label><label class="filter-field">处理状态<select v-model="filters.status"><option value="">全部状态</option><option value="PARSING">等待处理</option><option value="READY">READY</option><option value="FAILED">FAILED</option></select></label><button class="button primary">查询</button></form>
        <div v-if="loading" class="loading-state">正在加载资料台账…</div>
        <div v-else-if="documents.items.length === 0" class="empty-state">暂无资料，点击“上传新资料”登记第一份产品手册或参数表。</div>
        <div v-else class="document-list">
          <article v-for="item in documents.items" :key="item.id" class="document-row">
            <div class="file-glyph">{{ item.file_type }}</div>
            <div class="document-main"><div class="title-line"><h3>{{ item.document_name }}</h3><ElTag :type="item.parse_status === 'FAILED' ? 'danger' : item.parse_status === 'READY' ? 'success' : 'primary'" effect="plain" size="small">{{ stateLabel(item.parse_status) }}</ElTag></div><p>{{ item.original_name }} · <span class="numeric">{{ sizeLabel(item.file_size) }}</span></p><div class="meta"><span>{{ item.security_level === 'PUBLIC' ? '公开' : item.security_level === 'INTERNAL' ? '内部' : '受限' }}</span><span v-for="role in item.allowed_roles" :key="role">{{ role === 'PRODUCT_MANAGER' ? '产品经理' : role === 'SALES' ? '销售' : '管理员' }}</span></div><small>产品：{{ item.product_ids.map(id => productCache[id] ?? productNames.get(id) ?? id).join('、') || '未关联' }} · 上传于 {{ dateLabel(item.created_at) }}</small><small v-if="item.parse_status === 'FAILED' && item.parse_error" class="parse-error">原因：{{ item.parse_error }}；请检查文件格式、权限和原始资料后重试。</small></div>
            <div class="row-actions"><button class="button" @click="download(item)">下载</button><button class="button" @click="beginPermission(item)">权限</button><ElPopconfirm title="删除后文件与关联记录将一并移除，确认继续？" confirm-button-text="删除" cancel-button-text="取消" width="260" @confirm="remove(item)"><template #reference><button class="button danger">删除</button></template></ElPopconfirm></div>
          </article>
        </div>
      </section>
    </div>
    <ElDialog v-model="permissionOpen" title="调整资料访问权限" width="520px">
      <div v-if="editing" class="permission-form"><p><b>{{ editing.document_name }}</b><br /><small>保存后文件列表、详情、下载和检索权限立即生效；移除角色也会撤回其片段检索与历史引用。</small><br /><small>仅有来源级公开片段权限、从未拥有原文件权限的角色不受本次文件权限调整影响。</small></p><label class="form-field">安全等级<select v-model="permission.security"><option value="PUBLIC">公开</option><option value="INTERNAL">内部</option><option value="RESTRICTED">受限</option></select></label><fieldset><legend>允许角色</legend><label class="check"><input type="checkbox" checked disabled /> 管理员</label><label class="check"><input v-model="permission.roles" type="checkbox" value="PRODUCT_MANAGER" /> 产品经理</label><label class="check"><input v-model="permission.roles" type="checkbox" value="SALES" /> 销售</label></fieldset></div>
      <template #footer><button class="button" @click="editing = null">取消</button><button class="button primary" :disabled="savingPermission" @click="savePermission">{{ savingPermission ? '保存中…' : '保存权限' }}</button></template>
    </ElDialog>
  </section>
</template>

<style scoped>
.document-workspace { display: block; }
.heading-actions { display: flex; align-items: center; gap: 16px; }
.limit-note { display: grid; grid-template-columns: auto 1fr; align-items: baseline; gap: 0 10px; min-width: 180px; padding-left: 16px; border-left: 3px solid var(--color-accent); }
.limit-note b { font-size: 22px; }
.limit-note span, .limit-note small { color: var(--color-text-tertiary); font-size: 10px; }
.limit-note small { grid-column: 1 / -1; margin-top: 3px; }
.drawer-backdrop { position: fixed; z-index: 80; inset: 0; display: flex; justify-content: flex-end; background: rgba(20,19,18,.22); backdrop-filter: blur(2px); }
.upload-panel { position: relative; display: grid; align-content: start; gap: 14px; width: min(440px, 92vw); height: 100%; padding: 28px; overflow-y: auto; border-radius: 0; animation: drawer-in 220ms ease-out; }
.drawer-close { position: absolute; top: 14px; right: 14px; display: grid; place-items: center; width: 36px; height: 36px; border: 1px solid var(--color-border); border-radius: 50%; background: var(--color-surface); color: var(--color-text-primary); cursor: pointer; font-size: 20px; }
@keyframes drawer-in { from { transform: translateX(32px); opacity: .4; } to { transform: translateX(0); opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .upload-panel { animation: none; } }
.panel-title { display: flex; align-items: flex-start; gap: 10px; }
.panel-title h2 { margin: 0; font-size: 16px; }
.panel-title p { margin: 4px 0 0; color: var(--color-text-tertiary); font-size: 11px; }
.step { display: grid; place-items: center; flex: none; width: 28px; height: 28px; border-radius: 8px; background: var(--color-accent-soft); color: var(--color-accent); font-size: 10px; font-weight: 800; }
.drop-zone { position: relative; display: grid; gap: 5px; padding: 16px; overflow: hidden; border: 1px dashed var(--color-accent); border-radius: 9px; background: var(--color-accent-soft); color: var(--color-accent); cursor: pointer; }
.drop-zone input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.drop-zone b { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.drop-zone small { color: var(--color-text-secondary); font-size: 10px; }
fieldset { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; border: 0; }
legend { width: 100%; margin-bottom: 3px; color: var(--color-text-secondary); font-size: 12px; font-weight: 600; }
.check { display: flex; align-items: center; gap: 5px; color: var(--color-text-secondary); font-size: 10px; }
.ledger { min-width: 0; overflow: hidden; }
.ledger-filters { display: grid; grid-template-columns: minmax(180px, 1fr) 120px 140px auto; gap: 8px; align-items: end; padding: 14px 18px; border-bottom: 1px solid var(--color-border-soft); }
.ledger-filters .filter-field { min-width: 0; }
.document-list { padding: 0 18px; }
.document-row { display: grid; grid-template-columns: 48px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 15px 0; border-bottom: 1px solid var(--color-border-soft); }
.document-row:last-child { border-bottom: 0; }
.file-glyph { display: grid; place-items: center; height: 42px; border-radius: 8px; background: var(--color-surface-inset); color: var(--color-accent); font-size: 9px; font-weight: 800; }
.document-main { min-width: 0; }
.title-line { display: flex; align-items: center; gap: 8px; }
.title-line h3 { min-width: 0; margin: 0; overflow: hidden; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.document-main p { margin: 4px 0; color: var(--color-text-secondary); font-size: 10px; }
.meta { display: flex; flex-wrap: wrap; gap: 5px; margin: 7px 0; }
.meta span { padding: 3px 6px; border-radius: 4px; background: var(--color-surface-inset); color: var(--color-text-secondary); font-size: 9px; }
.document-main small { display: block; overflow: hidden; color: var(--color-text-tertiary); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.document-main .parse-error { margin-top: 5px; color: var(--color-danger); white-space: normal; }
.row-actions { display: flex; gap: 6px; }
.row-actions .button { min-height: 34px; padding: 6px 9px; font-size: 11px; }
.permission-form { display: grid; gap: 16px; }
.permission-form p { margin: 0; }
.permission-form small { color: var(--color-text-tertiary); }
.usage-note { margin: 4px 0 8px; color: var(--color-text-tertiary); font-size: 10px; line-height: 1.5; }
.product-picker { display: grid; gap: 7px; }
.selected-products { display: flex; flex-wrap: wrap; gap: 5px; min-height: 28px; }
.selected-product { display: inline-flex; align-items: center; gap: 5px; padding: 4px 7px; border-radius: 5px; background: var(--color-accent-soft); color: var(--color-accent); font-size: 10px; }
.selected-product button { border: 0; background: transparent; color: inherit; cursor: pointer; font-weight: 700; }
.empty-selection { color: var(--color-text-tertiary); font-size: 10px; }
.product-picker-list { display: grid; gap: 4px; max-height: 160px; overflow-y: auto; padding: 5px; border: 1px solid var(--color-border-soft); border-radius: 7px; }
.product-picker-list > span { padding: 8px; color: var(--color-text-tertiary); font-size: 10px; }
.product-option { padding: 7px 8px; border: 0; border-radius: 5px; background: transparent; color: var(--color-text-primary); cursor: pointer; text-align: left; font-size: 10px; }
.product-option:hover, .product-option.selected { background: var(--color-accent-soft); color: var(--color-accent); }
.product-more { padding: 7px 8px; border: 1px solid var(--color-border-soft); border-radius: 5px; background: var(--color-surface-subtle); color: var(--color-text-secondary); cursor: pointer; font-size: 10px; }
</style>
