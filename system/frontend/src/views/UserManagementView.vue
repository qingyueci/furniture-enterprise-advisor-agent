<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createUser, deleteUsers, fetchUsers, permanentlyDeleteUser, restoreUser, updateUser, type UserListData } from '../api/users'
import { messageFor } from '../api/http'
import type { CurrentUser, Role, UserStatus } from '../api/auth'

const data = ref<UserListData>({ items: [], pagination: { page: 1, page_size: 20, total: 0 } })
const filters = reactive<{ keyword: string; role: Role | ''; status: UserStatus | ''; page: number }>({ keyword: '', role: '', status: '', page: 1 })
const newUser = reactive<{ username: string; password: string; role: Role; status: UserStatus }>({ username: '', password: '', role: 'SALES', status: 'ACTIVE' })
const editing = ref<CurrentUser | null>(null)
const update = reactive<{ role: Role; status: UserStatus; newPassword: string }>({ role: 'SALES', status: 'ACTIVE', newPassword: '' })
const message = ref('')
const error = ref('')
const loading = ref(false)
const activeTab = ref<'list' | 'create'>('list')
const managementMode = ref(false)
const showDeleted = ref(false)
const selectedIds = ref<string[]>([])
const deleting = ref(false)
let listRequest = 0

async function load(page = 1) {
  const request = ++listRequest
  loading.value = true; error.value = ''; filters.page = page; selectedIds.value = []; editing.value = null
  try {
    const result = await fetchUsers({ keyword: filters.keyword || undefined, role: filters.role || undefined, status: filters.status || undefined, include_deleted: showDeleted.value, page, page_size: 20 })
    if (request === listRequest) data.value = result
  } catch (exception) { if (request === listRequest) error.value = messageFor(exception) }
  finally { if (request === listRequest) loading.value = false }
}
async function add() { message.value = ''; error.value = ''; try { await createUser({ ...newUser }); message.value = '用户已创建。'; newUser.username = ''; newUser.password = ''; openList(); await load(1) } catch (exception) { error.value = messageFor(exception) } }
function beginEdit(user: CurrentUser) { editing.value = user; update.role = user.role; update.status = user.status; update.newPassword = '' }
function closeEdit() {
  if (editing.value && (update.role !== editing.value.role || update.status !== editing.value.status || update.newPassword) && !window.confirm('关闭后未保存的用户修改将丢失，确认关闭？')) return
  editing.value = null
}
async function save() { if (!editing.value) return; message.value = ''; error.value = ''; try { await updateUser(editing.value.id, { role: update.role, status: update.status, new_password: update.newPassword || undefined }); message.value = '用户已更新。'; editing.value = null; await load(filters.page) } catch (exception) { error.value = messageFor(exception) } }
function reset() { filters.keyword = ''; filters.role = ''; filters.status = ''; void load(1) }
function toggleSelected(id: string) { selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id] }
function toggleAll() { const ids = data.value.items.map(item => item.id); selectedIds.value = selectedIds.value.length === ids.length ? [] : ids }
async function removeSelected() {
  if (!selectedIds.value.length || deleting.value || !window.confirm(`确认删除选中的 ${selectedIds.value.length} 个用户？账号会立即失效。`)) return
  deleting.value = true; error.value = ''
  try { await deleteUsers(selectedIds.value); await load(filters.page) }
  catch (exception) { error.value = messageFor(exception) }
  finally { deleting.value = false }
}
async function restoreSelected() {
  if (selectedIds.value.length !== 1 || deleting.value) return
  deleting.value = true; error.value = ''
  try { await restoreUser(selectedIds.value[0]); await load(filters.page) }
  catch (exception) { error.value = messageFor(exception) }
  finally { deleting.value = false }
}
async function permanentlyRemoveSelected() {
  if (selectedIds.value.length !== 1 || deleting.value || !window.confirm('永久删除该用户？存在关联资料或会话时操作会被阻止。')) return
  deleting.value = true; error.value = ''
  try { await permanentlyDeleteUser(selectedIds.value[0]); await load(filters.page) }
  catch (exception) { error.value = messageFor(exception) }
  finally { deleting.value = false }
}
function editSelected() { if (!showDeleted.value && selectedIds.value.length === 1) { const user = data.value.items.find(item => item.id === selectedIds.value[0]); if (user) beginEdit(user) } }
function openList() { activeTab.value = 'list'; selectedIds.value = []; editing.value = null }
function openCreate() { activeTab.value = 'create'; managementMode.value = false; selectedIds.value = []; editing.value = null }
function toggleManagement() { if (activeTab.value === 'create') activeTab.value = 'list'; managementMode.value = !managementMode.value; selectedIds.value = []; editing.value = null }
function toggleSelectedFromRow(id: string) { if (managementMode.value) toggleSelected(id) }
function handleRowKeydown(event: KeyboardEvent, id: string) { if (!managementMode.value) return; if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggleSelected(id) } }
async function switchDeleted(value: boolean) { showDeleted.value = value; selectedIds.value = []; editing.value = null; await load(1) }
onMounted(() => load(1))
</script>

<template>
  <section class="page">
    <header class="page-heading management-heading"><div><span class="kicker">ADMIN · ACCESS CONTROL</span><h1>用户管理</h1><p>维护用户名、角色和账号状态；权限边界仍由后端 RBAC 最终执行。</p></div><span class="state accent">ADMIN ONLY</span></header>
    <nav class="user-navigation" aria-label="用户管理导航">
      <button id="users-list-nav" type="button" :class="['button', { primary: activeTab === 'list' }]" :aria-current="activeTab === 'list' ? 'page' : undefined" aria-controls="users-list-panel" @click="openList">用户列表</button>
      <button id="users-create-nav" type="button" :class="['button', { primary: activeTab === 'create' }]" :aria-current="activeTab === 'create' ? 'page' : undefined" aria-controls="users-create-panel" @click="openCreate">创建用户</button>
      <button id="users-management-nav" type="button" :class="['button', { primary: managementMode }]" :aria-pressed="managementMode" aria-controls="users-list-panel" @click="toggleManagement">{{ managementMode ? '完成管理' : '精确管理' }}</button>
    </nav>
    <p v-if="message" class="success-banner" role="status">{{ message }}</p><p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <section v-show="activeTab === 'list'" id="users-list-panel" aria-labelledby="users-list-nav">
    <div class="management-toolbar"><div class="actions"><button type="button" :class="['button', { primary: !showDeleted }]" @click="switchDeleted(false)">正常用户</button><button type="button" :class="['button', { primary: showDeleted }]" @click="switchDeleted(true)">已删除用户</button></div><div v-if="managementMode" class="actions"><label class="check"><input type="checkbox" :checked="data.items.length > 0 && selectedIds.length === data.items.length" @change="toggleAll" /> 全选当前页</label><span class="selection-count">已选 {{ selectedIds.length }} 项</span><template v-if="!showDeleted"><button class="button" :disabled="selectedIds.length !== 1 || deleting" @click="editSelected">编辑</button><button class="button danger" :disabled="!selectedIds.length || deleting" @click="removeSelected">删除选中（{{ selectedIds.length }}）</button></template><template v-else><button class="button" :disabled="selectedIds.length !== 1 || deleting" @click="restoreSelected">恢复</button><button class="button danger" :disabled="selectedIds.length !== 1 || deleting" @click="permanentlyRemoveSelected">永久删除</button></template></div></div>
    <form class="filter-bar panel" @submit.prevent="load(1)"><label class="filter-field grow">用户名<input v-model="filters.keyword" placeholder="按用户名筛选" maxlength="50" /></label><label class="filter-field">角色<select v-model="filters.role"><option value="">全部角色</option><option value="ADMIN">ADMIN</option><option value="PRODUCT_MANAGER">PRODUCT_MANAGER</option><option value="SALES">SALES</option></select></label><label class="filter-field">状态<select v-model="filters.status"><option value="">全部状态</option><option value="ACTIVE">ACTIVE</option><option value="DISABLED">DISABLED</option></select></label><div class="actions"><button class="button primary" :disabled="loading">查询</button><button class="button" type="button" @click="reset">重置</button></div></form>
    <div class="table-wrap"><div v-if="loading" class="loading-state">正在加载用户…</div><div v-else-if="!data.items.length" class="empty-state">暂无匹配用户。</div><table v-else class="data-table"><thead><tr><th v-if="managementMode">选择</th><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="user in data.items" :key="user.id" :class="{ 'selectable-row': managementMode, 'selected-row': managementMode && selectedIds.includes(user.id) }" :aria-selected="managementMode ? selectedIds.includes(user.id) : undefined" :tabindex="managementMode ? 0 : undefined" @click="toggleSelectedFromRow(user.id)" @keydown="handleRowKeydown($event, user.id)"><td v-if="managementMode"><input type="checkbox" :checked="selectedIds.includes(user.id)" :aria-label="'选择用户 ' + user.username" @click.stop @keydown.stop @change="toggleSelected(user.id)" /></td><td><strong>{{ user.username }}</strong></td><td>{{ user.role }}</td><td><span :class="['state', user.status === 'ACTIVE' ? 'success' : 'error']">{{ user.status }}</span></td><td class="numeric">{{ new Date(user.created_at).toLocaleString('zh-CN', { hour12: false }) }}</td><td class="toolbar-hint">{{ managementMode ? '点击整行选择，使用上方工具栏操作' : '进入精确管理后选择' }}</td></tr></tbody></table></div>
    <footer class="pagination"><span>共 <b class="numeric">{{ data.pagination.total }}</b> 个用户</span><div class="pagination-actions"><button class="button" :disabled="loading || filters.page <= 1" @click="load(filters.page - 1)">上一页</button><button class="button" :disabled="loading || filters.page * data.pagination.page_size >= data.pagination.total" @click="load(filters.page + 1)">下一页</button></div></footer>

    </section>
    <section v-show="activeTab === 'create'" id="users-create-panel" aria-labelledby="users-create-nav" class="create-panel"><form class="panel form-panel" @submit.prevent="add"><div><span class="kicker">CREATE</span><h2>创建用户</h2></div><label class="form-field">用户名<input v-model="newUser.username" required minlength="3" maxlength="50" /></label><label class="form-field">初始密码<input v-model="newUser.password" type="password" autocomplete="new-password" required minlength="8" maxlength="64" /></label><label class="form-field">角色<select v-model="newUser.role"><option value="ADMIN">ADMIN</option><option value="PRODUCT_MANAGER">PRODUCT_MANAGER</option><option value="SALES">SALES</option></select></label><label class="form-field">状态<select v-model="newUser.status"><option value="ACTIVE">ACTIVE</option><option value="DISABLED">DISABLED</option></select></label><button class="button primary">创建用户</button></form></section>
    <div v-if="editing" class="drawer-backdrop" @click.self="closeEdit"><form class="edit-drawer panel" role="dialog" aria-modal="true" :aria-label="'编辑用户 ' + editing.username" @submit.prevent="save"><button class="drawer-close" type="button" aria-label="关闭编辑" @click="closeEdit">×</button><div><span class="kicker">UPDATE</span><h2>编辑 {{ editing.username }}</h2></div><label class="form-field">角色<select v-model="update.role"><option value="ADMIN">ADMIN</option><option value="PRODUCT_MANAGER">PRODUCT_MANAGER</option><option value="SALES">SALES</option></select></label><label class="form-field">状态<select v-model="update.status"><option value="ACTIVE">ACTIVE</option><option value="DISABLED">DISABLED</option></select></label><label class="form-field">重置密码（留空不变）<input v-model="update.newPassword" type="password" autocomplete="new-password" minlength="8" maxlength="64" /></label><div class="actions"><button class="button primary">保存更新</button><button class="button" type="button" @click="closeEdit">取消</button></div></form></div>
  </section>
</template>

<style scoped>
.user-navigation { position: sticky; top: var(--topbar-height); z-index: 10; display: flex; gap: 20px; margin-bottom: 20px; padding: 10px 0 0; border-bottom: 1px solid var(--color-border); background: var(--color-canvas); }
.user-navigation .button { position: relative; border: 0; border-radius: 0; background: transparent; color: rgba(242,236,226,.76); box-shadow: none; }
.user-navigation .button::after { position: absolute; right: 0; bottom: -1px; left: 0; height: 2px; content: ''; background: var(--color-accent); transform: scaleX(0); transition: transform 160ms ease; }
.user-navigation .button.primary { background: rgba(242,236,226,.1); color: var(--color-surface); }
.user-navigation .button.primary::after { transform: scaleX(1); }
.create-panel { max-width: 640px; }
.management-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.management-toolbar .check { color: var(--color-text-secondary); font-size: 11px; }
.selection-count, .toolbar-hint { color: var(--color-text-tertiary); font-size: 10px; }
.selectable-row { cursor: pointer; }
.selectable-row:focus-visible { outline: 2px solid var(--color-focus); outline-offset: -2px; }
.data-table tbody tr.selected-row { background: var(--color-accent-soft); }
.data-table tbody tr.selected-row:hover { background: var(--color-accent-soft); }
.row-actions { display: flex; flex-wrap: wrap; gap: 5px; }
.drawer-backdrop { position: fixed; z-index: 80; inset: 0; display: flex; justify-content: flex-end; background: rgba(20,19,18,.22); backdrop-filter: blur(2px); }
.edit-drawer { position: relative; display: grid; align-content: start; gap: 18px; width: min(420px, 92vw); height: 100%; padding: 30px; border-radius: 0; animation: drawer-in 220ms ease-out; }
.drawer-close { position: absolute; top: 14px; right: 14px; display: grid; place-items: center; width: 36px; height: 36px; border: 1px solid var(--color-border); border-radius: 50%; background: var(--color-surface); cursor: pointer; font-size: 20px; }
@keyframes drawer-in { from { transform: translateX(32px); opacity: .4; } to { transform: translateX(0); opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .edit-drawer, .user-navigation .button::after { animation: none; transition: none; } }
@media (max-width: 800px) { .management-toolbar { align-items: flex-start; flex-direction: column; } }
</style>
