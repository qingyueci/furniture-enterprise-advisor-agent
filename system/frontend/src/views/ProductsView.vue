<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElDrawer } from 'element-plus'
import { createProduct, deleteProduct, deleteProducts, fetchPrices, fetchProduct, fetchProductOptions, fetchProducts, permanentlyDeleteProduct, restoreProduct, updateProduct, type Product, type ProductInput, type ProductListData, type ProductType, type PriceType, type ProductPricesData } from '../api/products'
import { messageFor } from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const products = ref<ProductListData>({ items: [], pagination: { page: 1, page_size: 20, total: 0 } })
const filters = reactive<{ keyword: string; brand: string; category: string; page: number }>({ keyword: '', brand: '', category: '', page: 1 })
const loading = ref(false)
const error = ref('')
const selected = ref<Product | null>(null)
const prices = ref<ProductPricesData | null>(null)
const priceLoading = ref(false)
const requestedType = ref<PriceType | ''>('')
const canViewInternal = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'PRODUCT_MANAGER')
const canManage = computed(() => canViewInternal.value)
const managementMode = ref(false)
const showDeleted = ref(false)
const selectedIds = ref<number[]>([])
const options = ref<{ brands: string[]; categories: string[] }>({ brands: [], categories: [] })
const formOpen = ref(false)
const detailOpen = computed({ get: () => selected.value !== null, set: value => { if (!value) closeDetail() } })
const editingId = ref<number | null>(null)
const saving = ref(false)
const deleting = ref(false)
const form = reactive<ProductInput>({ product_name: '', model: '', category: '', brand: '', product_type: 'INTERNAL', description: '' })
let listRequest = 0
let detailRequest = 0
let priceRequest = 0

async function search(page = 1) {
  const request = ++listRequest
  loading.value = true; error.value = ''; filters.page = page
  selectedIds.value = []
  try {
    const result = await fetchProducts({ keyword: filters.keyword || undefined, brand: filters.brand || undefined, category: filters.category || undefined, include_deleted: showDeleted.value, page, page_size: 20 })
    if (request === listRequest) products.value = result
  }
  catch (exception) { if (request === listRequest) error.value = messageFor(exception) }
  finally { if (request === listRequest) loading.value = false }
}
async function showProduct(product: Product) {
  const request = ++detailRequest
  error.value = ''; selected.value = null; prices.value = null; requestedType.value = ''
  try {
    const result = await fetchProduct(product.id)
    if (request !== detailRequest) return
    selected.value = result
    await loadPrices(request)
  } catch (exception) { if (request === detailRequest) error.value = messageFor(exception) }
}
async function loadPrices(parentRequest = detailRequest) {
  if (!selected.value) return
  const request = parentRequest
  const priceRun = ++priceRequest
  priceLoading.value = true; error.value = ''
  try {
    const result = await fetchPrices(selected.value.id, requestedType.value || undefined)
    if (request === detailRequest && priceRun === priceRequest) prices.value = result
  }
  catch (exception) {
    if (request !== detailRequest || priceRun !== priceRequest) return
    prices.value = null
    // A product may be catalogued from a source record before it has a
    // structured, role-visible price.  The detail panel states that case.
    const message = messageFor(exception)
    if (request === detailRequest && !message.includes('没有价格数据')) error.value = message
  } finally { if (request === detailRequest && priceRun === priceRequest) priceLoading.value = false }
}
function onPriceTypeChange() { void loadPrices(detailRequest) }
function displayDate(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
function descriptionCards(value: string | null) {
  const text = value?.trim() || '暂无产品说明。'
  const labels = ['基材/材质', '饰面/工艺', '厚度(mm)', '宽度(mm)', '高度(mm)', '深度(mm)', '环保等级', '适用空间', '不适用/限制条件', '产品状态', '型号', '来源', '原记录']
  const escaped = labels.map(label => label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  const nextField = new RegExp(`(?:[；;]|\\r?\\n|[\\t\\u00a0 ]+)[\\t\\u00a0 ]*(?=(?:${escaped})[：:])`, 'g')
  return text.replace(/\r\n?/g, '\n').replace(nextField, '\n').split(/\n+/).map(item => item.trim()).filter(Boolean)
}
function reset() { filters.keyword = ''; filters.brand = ''; filters.category = ''; void search(1) }
function toggleSelected(id: number) { selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id] }
function toggleAll() { const ids = products.value.items.map(item => item.id); selectedIds.value = selectedIds.value.length === ids.length ? [] : ids }
function resetForm() { form.product_name = ''; form.model = ''; form.category = ''; form.brand = ''; form.product_type = 'INTERNAL'; form.description = '' }
function beginCreate() { editingId.value = null; resetForm(); formOpen.value = true }
function beginEdit(product: Product) { editingId.value = product.id; form.product_name = product.product_name; form.model = product.model; form.category = product.category ?? ''; form.brand = product.brand; form.product_type = product.product_type; form.description = product.description ?? ''; formOpen.value = true }
function closeForm(done?: () => void) {
  if ((form.product_name || form.model || form.brand || form.category || form.description) && !window.confirm('关闭后未保存的产品信息将丢失，确认关闭？')) return
  formOpen.value = false; done?.()
}
async function saveProduct() { saving.value = true; error.value = ''; try { if (editingId.value === null) await createProduct(form); else await updateProduct(editingId.value, form); formOpen.value = false; await search(filters.page) } catch (exception) { error.value = messageFor(exception) } finally { saving.value = false } }
async function removeProduct(product: Product) { if (deleting.value || !window.confirm(`确认删除产品“${product.product_name}”？`)) return; deleting.value = true; try { await deleteProduct(product.id); await search(filters.page); if (selected.value?.id === product.id) closeDetail() } catch (exception) { error.value = messageFor(exception) } finally { deleting.value = false } }
async function removeSelected() { if (!selectedIds.value.length || deleting.value || !window.confirm(`确认删除选中的 ${selectedIds.value.length} 个产品？`)) return; deleting.value = true; try { await deleteProducts(selectedIds.value); await search(filters.page) } catch (exception) { error.value = messageFor(exception) } finally { deleting.value = false } }
async function restore(product: Product) { if (deleting.value) return; deleting.value = true; try { await restoreProduct(product.id); await search(filters.page) } catch (exception) { error.value = messageFor(exception) } finally { deleting.value = false } }
async function permanentlyRemove(product: Product) { if (deleting.value || !window.confirm(`永久删除“${product.product_name}”？存在关联时操作会被阻止。`)) return; deleting.value = true; try { await permanentlyDeleteProduct(product.id); await search(filters.page) } catch (exception) { error.value = messageFor(exception) } finally { deleting.value = false } }
function closeDetail() { detailRequest += 1; priceRequest += 1; selected.value = null; prices.value = null }
async function switchDeleted(value: boolean) { showDeleted.value = value; selectedIds.value = []; closeDetail(); await search(1) }
onMounted(async () => { try { options.value = await fetchProductOptions() } catch (exception) { error.value = messageFor(exception) }; await search(1) })
</script>

<template>
  <section class="page">
    <header class="page-heading"><div><span class="kicker">PRODUCT CATALOG</span><h1>产品与价格</h1><p>产品基础信息与结构化价格分开呈现，金额保持后端两位小数字符串。</p></div><span class="state accent">{{ auth.user?.role }}</span></header>
    <div class="catalog-tools">
      <form class="filter-bar panel" @submit.prevent="search(1)"><label class="filter-field grow">产品或型号<input v-model="filters.keyword" placeholder="输入产品名称、型号或资料编号" maxlength="50" /></label><label class="filter-field">品牌<select v-model="filters.brand"><option value="">全部品牌</option><option v-for="brand in options.brands" :key="brand" :value="brand">{{ brand }}</option></select></label><label class="filter-field">产品类别<select v-model="filters.category"><option value="">全部类别</option><option v-for="category in options.categories" :key="category" :value="category">{{ category }}</option></select></label><div class="actions"><button class="button primary" :disabled="loading">查询</button><button class="button" type="button" @click="reset">重置</button></div></form>
      <div class="catalog-actions"><div class="actions"><button class="button" :class="{ primary: !showDeleted }" @click="switchDeleted(false)">现有产品</button><button v-if="canManage" class="button" :class="{ primary: showDeleted }" @click="switchDeleted(true)">已删除</button></div><div v-if="canManage" class="actions"><button class="button" @click="beginCreate">新增产品</button><button class="button" :class="{ primary: managementMode }" @click="managementMode = !managementMode; selectedIds = []">{{ managementMode ? '完成管理' : '管理产品' }}</button><label v-if="managementMode" class="check"><input type="checkbox" :checked="products.items.length > 0 && selectedIds.length === products.items.length" @change="toggleAll" /> 全选当前页</label><span v-if="managementMode" class="selection-count">已选 {{ selectedIds.length }} 项</span><button v-if="managementMode && !showDeleted" class="button danger" :disabled="!selectedIds.length || deleting" @click="removeSelected">删除选中（{{ selectedIds.length }}）</button></div></div>
    </div>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <div class="catalog-layout">
      <div>
        <div class="table-wrap"><div v-if="loading" class="loading-state">正在查询产品…</div><div v-else-if="!products.items.length" class="empty-state">暂无匹配产品。</div><table v-else class="data-table"><thead><tr><th v-if="managementMode">选择</th><th>产品</th><th>型号 / 资料编号</th><th>品牌</th><th>产品类别</th><th>操作</th></tr></thead><tbody><tr v-for="product in products.items" :key="product.id"><td v-if="managementMode"><input type="checkbox" :checked="selectedIds.includes(product.id)" :aria-label="'选择产品 ' + product.product_name" @change="toggleSelected(product.id)" /></td><td><strong>{{ product.product_name }}</strong></td><td>{{ product.model.startsWith('ENT-') ? '资料编号 ' + product.model + '（型号未提供）' : product.model }}</td><td>{{ product.brand }}</td><td>{{ product.category || '未分类' }}</td><td><div class="row-actions"><button v-if="!showDeleted" class="button" @click="showProduct(product)">查看资料与价格</button><template v-if="managementMode && canManage"><button v-if="!showDeleted" class="button" :disabled="deleting" @click="beginEdit(product)">编辑</button><button v-if="!showDeleted" class="button danger" :disabled="deleting" @click="removeProduct(product)">删除</button><button v-if="showDeleted" class="button" :disabled="deleting" @click="restore(product)">恢复</button><button v-if="showDeleted" class="button danger" :disabled="deleting" @click="permanentlyRemove(product)">永久删除</button></template></div></td></tr></tbody></table></div>
        <footer class="pagination"><span>共 <b class="numeric">{{ products.pagination.total }}</b> 个产品</span><div class="pagination-actions"><button class="button" :disabled="loading || filters.page <= 1" @click="search(filters.page - 1)">上一页</button><button class="button" :disabled="loading || filters.page * products.pagination.page_size >= products.pagination.total" @click="search(filters.page + 1)">下一页</button></div></footer>
      </div>
    </div>
    <ElDrawer v-model="detailOpen" title="产品资料与价格" size="min(520px, 92vw)" direction="rtl" class="workspace-drawer">
      <aside v-if="selected" class="product-detail" aria-live="polite"><header><div><span class="kicker">PRODUCT DETAIL</span><h2>{{ selected.product_name }}</h2><p>{{ selected.model.startsWith('ENT-') ? '资料编号 ' + selected.model + '（型号未提供）' : selected.model }} · {{ selected.brand }}</p></div><div class="row-actions"><button v-if="canManage && !showDeleted" class="button" :disabled="deleting" @click="beginEdit(selected)">编辑</button><button v-if="canManage && !showDeleted" class="button danger" :disabled="deleting" @click="removeProduct(selected)">删除</button></div></header><div class="description" aria-label="产品说明"><p v-for="(item, index) in descriptionCards(selected.description)" :key="index" class="description-card">{{ item }}</p></div><label class="form-field">价格类型<select v-model="requestedType" @change="onPriceTypeChange"><option value="">全部可见类型</option><option value="GUIDE">GUIDE</option><option value="SALES">SALES</option><option v-if="canViewInternal" value="INTERNAL_QUOTE">INTERNAL_QUOTE</option></select></label><div v-if="priceLoading" class="loading-state">正在加载价格…</div><div v-else-if="prices?.prices.length" class="price-list"><article v-for="price in prices.prices" :key="price.id"><span class="state accent">{{ price.price_type }}</span><strong class="numeric">{{ price.price }} <small>{{ price.currency }}/{{ price.pricing_unit ?? '单位未提供' }}</small></strong><p>{{ price.quote_spec ?? '规格未提供' }}；{{ price.included_scope ?? '包含范围未提供' }}</p><p>{{ price.source }}</p><time class="numeric">{{ displayDate(price.update_time) }}</time></article></div><div v-else class="empty-state">暂无结构化价格；不使用缺失单位或未确认口径的供应商报价补填。</div></aside>
    </ElDrawer>
    <ElDrawer v-model="formOpen" :title="editingId === null ? '新增产品' : '编辑产品'" size="min(520px, 92vw)" direction="rtl" :before-close="closeForm" class="workspace-drawer">
      <form class="product-form" @submit.prevent="saveProduct"><p>型号、资料编号和产品类别分开填写；资料缺少型号时不要用资料编号冒充型号。</p><div class="form-grid"><label class="form-field">产品名称<input v-model="form.product_name" required maxlength="120" /></label><label class="form-field">型号<input v-model="form.model" required maxlength="80" /></label><label class="form-field">品牌<input v-model="form.brand" required maxlength="80" /></label><label class="form-field">产品类别<input v-model="form.category" maxlength="80" list="product-form-category-options" /><datalist id="product-form-category-options"><option v-for="category in options.categories" :key="category" :value="category" /></datalist></label></div><label class="form-field">说明<textarea v-model="form.description" rows="7" maxlength="5000" /></label><div class="actions"><button class="button primary" :disabled="saving">{{ saving ? '保存中…' : '保存产品' }}</button><button class="button" type="button" @click="closeForm()">取消</button></div></form>
    </ElDrawer>
  </section>
</template>

<style scoped>
.catalog-layout { display: block; }
.catalog-tools { position: sticky; top: var(--topbar-height); z-index: 12; padding-top: 8px; background: var(--color-canvas); }
.catalog-tools .filter-bar { margin-bottom: 0; }
.product-detail { min-height: 280px; }
.product-detail header { display: flex; justify-content: space-between; gap: 12px; }
.product-detail h2 { margin: 5px 0 2px; font-size: 20px; }
.product-detail header p { margin: 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.65; }
.description { display: grid; gap: 7px; margin: 16px 0; padding-bottom: 14px; border-bottom: 1px solid var(--color-border-soft); }
.description-card { margin: 0; padding: 8px 10px; border: 1px solid var(--color-border-soft); border-radius: 8px; background: var(--color-surface-subtle); color: var(--color-text-secondary); font-size: 12px; line-height: 1.55; }
.price-list { display: grid; gap: 9px; margin-top: 14px; }
.price-list article { padding: 12px; border: 1px solid var(--color-border-soft); border-radius: 9px; background: var(--color-surface-subtle); }
.price-list strong { display: block; margin: 8px 0 3px; font-size: 19px; }
.price-list strong small { color: var(--color-text-secondary); font-size: 10px; }
.price-list p, .price-list time { display: block; margin: 0; color: var(--color-text-tertiary); font-size: 10px; line-height: 1.5; }
.catalog-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; }
.product-form { display: grid; gap: 16px; }
.product-form h2 { margin: 4px 0; font-size: 17px; }.product-form p { margin: 0; color: var(--color-text-tertiary); font-size: 11px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.product-form textarea { width: 100%; resize: vertical; }
.row-actions { display: flex; flex-wrap: wrap; gap: 5px; }
.selection-count { color: var(--color-text-tertiary); font-size: 10px; }
@media (max-width: 800px) { .form-grid { grid-template-columns: 1fr; } .catalog-actions { align-items: flex-start; flex-direction: column; } }
</style>
