<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { deleteConversations, fetchConversation, fetchConversations, fetchDeletedConversations, permanentlyDeleteConversation, restoreConversation, sendAgentMessage, type ConversationMessage, type ConversationSummary } from '../api/agent'
import { messageFor } from '../api/http'
import AgentMessage from '../components/AgentMessage.vue'
import CitationList from '../components/CitationList.vue'
import ToolCallList from '../components/ToolCallList.vue'
import { capabilitySnapshot, candidateCapabilities, confirmedStableCapabilities, materialBoundaries, usageConditions, verifiedIssues } from '../config/agentCapabilityProfile'

const conversations = ref<ConversationSummary[]>([])
const conversationPage = ref(1)
const conversationTotal = ref(0)
const activeId = ref<string | null>(null)
const messages = ref<ConversationMessage[]>([])
const selectedMessageId = ref<string | null>(null)
const loadingList = ref(false)
const loadingMessages = ref(false)
const sending = ref(false)
const deletingId = ref<string | null>(null)
const managementMode = ref(false)
const showDeleted = ref(false)
const selectedConversationIds = ref<string[]>([])
const error = ref('')
const pendingQuestion = ref('')
const evidenceVisible = ref(true)
const highlightedCitationRef = ref<string | null>(null)
const showLatest = ref(false)
const messageScroller = ref<HTMLElement | null>(null)
const showUsageGuide = ref(false)
let conversationRequest = 0
let conversationListRequest = 0
let highlightTimer: ReturnType<typeof setTimeout> | null = null
const picked = String(route.query.compare ?? '').split(',').filter(x => /^DEMO-[BD]\d{3}$/.test(x))
const draft = reactive({ message: typeof route.query.question === 'string' ? route.query.question.slice(0, 2000) : picked.length === 2 ? `比较 ${picked[0]} 和 ${picked[1]} 的参数、适用场景、限制和销售价` : '' })

const activeConversation = computed(() => conversations.value.find(item => item.id === activeId.value) ?? null)
const selectedEvidence = computed(() => {
  const selected = messages.value.find(item => item.id === selectedMessageId.value && item.role === 'ASSISTANT')
  return selected ?? [...messages.value].reverse().find(item => item.role === 'ASSISTANT') ?? null
})
const canLoadMore = computed(() => conversations.value.length < conversationTotal.value)

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

async function loadConversationList(reset = true) {
  const request = ++conversationListRequest
  loadingList.value = true
  error.value = ''
  try {
    const page = reset ? 1 : conversationPage.value + 1
    const result = showDeleted.value ? await fetchDeletedConversations(page, 20) : await fetchConversations(page, 20)
    if (request !== conversationListRequest) return
    conversations.value = reset ? result.items : [...conversations.value, ...result.items]
    conversationPage.value = page
    conversationTotal.value = result.pagination.total
  } catch (exception) { if (request === conversationListRequest) error.value = messageFor(exception, '会话列表加载失败。') }
  finally { if (request === conversationListRequest) loadingList.value = false }
}

async function selectConversation(id: string) {
  const request = ++conversationRequest
  activeId.value = id
  selectedMessageId.value = null
  highlightedCitationRef.value = null
  showUsageGuide.value = false
  loadingMessages.value = true
  error.value = ''
  try {
    let result = await fetchConversation(id, 1, 100)
    const lastPage = Math.max(1, Math.ceil(result.pagination.total / 100))
    if (lastPage > 1) result = await fetchConversation(id, lastPage, 100)
    if (request === conversationRequest && activeId.value === id) messages.value = result.messages
  } catch (exception) {
    if (request === conversationRequest) { messages.value = []; error.value = messageFor(exception, '会话历史加载失败。') }
  }
  finally {
    if (request === conversationRequest) {
      loadingMessages.value = false
      await scrollToLatest()
    }
  }
}

async function scrollToLatest() {
  await nextTick()
  const element = messageScroller.value
  if (!element) return
  element.scrollTo({ top: element.scrollHeight, behavior: scrollBehavior() })
  showLatest.value = false
}

function updateScrollState() {
  const element = messageScroller.value
  if (!element) return
  showLatest.value = element.scrollTop + element.clientHeight < element.scrollHeight - 48
}

async function selectCitation(messageId: string, ref: string) {
  selectedMessageId.value = messageId
  highlightedCitationRef.value = ref
  await nextTick()
  document.getElementById(`citation-card-${messageId}-${ref}`)?.scrollIntoView({ block: 'nearest', behavior: scrollBehavior() })
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlightedCitationRef.value = null }, 2400)
}

function newConversation() {
  if (sending.value || loadingMessages.value) return
  activeId.value = null
  messages.value = []
  selectedMessageId.value = null
  highlightedCitationRef.value = null
  draft.message = ''
  error.value = ''
  showUsageGuide.value = true
}

function fillExample(question: string) {
  draft.message = question
  showUsageGuide.value = false
}

async function refreshConversations() {
  if (sending.value || loadingMessages.value || loadingList.value) return
  await loadConversationList(true)
  if (activeId.value) await selectConversation(activeId.value)
}

function toggleConversationSelection(id: string) {
  selectedConversationIds.value = selectedConversationIds.value.includes(id)
    ? selectedConversationIds.value.filter(item => item !== id)
    : [...selectedConversationIds.value, id]
}

function toggleAllConversations() {
  const ids = conversations.value.map(item => item.id)
  selectedConversationIds.value = selectedConversationIds.value.length === ids.length ? [] : ids
}

async function deleteSelectedConversations() {
  if (!selectedConversationIds.value.length || sending.value || loadingMessages.value) return
  if (!window.confirm(`确认删除选中的 ${selectedConversationIds.value.length} 个会话？`)) return
  deletingId.value = 'bulk'; error.value = ''
  const removedActive = activeId.value !== null && selectedConversationIds.value.includes(activeId.value)
  try {
    await deleteConversations(selectedConversationIds.value)
    if (removedActive) newConversation()
    selectedConversationIds.value = []
    await loadConversationList(true)
  } catch (exception) { error.value = messageFor(exception, '批量删除会话失败，请稍后重试。') }
  finally { deletingId.value = null }
}

async function restoreDeletedConversation(item: ConversationSummary) {
  if (deletingId.value) return
  deletingId.value = item.id
  try { await restoreConversation(item.id); await loadConversationList(true) }
  catch (exception) { error.value = messageFor(exception, '恢复会话失败，请稍后重试。') }
  finally { deletingId.value = null }
}

async function permanentlyRemoveConversation(item: ConversationSummary) {
  if (deletingId.value || !window.confirm(`永久删除“${item.title}”？会话消息将被移除。`)) return
  deletingId.value = item.id
  try { await permanentlyDeleteConversation(item.id); await loadConversationList(true) }
  catch (exception) { error.value = messageFor(exception, '永久删除失败，请稍后重试。') }
  finally { deletingId.value = null }
}

async function submit() {
  const message = draft.message.trim()
  if (!message || sending.value || loadingMessages.value) return
  sending.value = true
  error.value = ''
  pendingQuestion.value = message
  try {
    const result = await sendAgentMessage({
      conversation_id: activeId.value ?? undefined,
      message,
    })
    draft.message = ''
    activeId.value = result.conversation_id
    await loadConversationList(true)
    await selectConversation(result.conversation_id)
    selectedMessageId.value = result.message_id
  } catch (exception) { error.value = messageFor(exception, 'Agent 请求未完成，请检查输入后重试。') }
  finally { sending.value = false; pendingQuestion.value = ''; await scrollToLatest() }
}

function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
}

async function switchDeletedView(value: boolean) {
  showDeleted.value = value
  selectedConversationIds.value = []
  activeId.value = null
  messages.value = []
  selectedMessageId.value = null
  highlightedCitationRef.value = null
  await loadConversationList(true)
}

onMounted(async () => {
  await loadConversationList(true)
  if (conversations.value[0]) await selectConversation(conversations.value[0].id)
  else showUsageGuide.value = true
})
</script>

<template>
  <section class="agent-page page">
    <div class="agent-stage">
    <div class="agent-heading">
      <div><span class="kicker">EVIDENCE WORKBENCH</span><h1>Agent 产品分析</h1><p>问题、结构化结果、引用与工具状态在同一工作区内核验。</p></div>
    </div>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

    <div :class="['agent-workbench', { 'evidence-hidden': !evidenceVisible }]">
      <aside class="conversation-rail panel" aria-label="会话列表">
        <div class="rail-head"><div><span>{{ showDeleted ? '已删除会话' : '我的会话' }}</span><b class="numeric">{{ conversationTotal }}</b></div><button class="rail-manage" type="button" :aria-pressed="managementMode" @click="managementMode = !managementMode; selectedConversationIds = []">{{ managementMode ? '完成' : '管理' }}</button></div>
        <div v-if="managementMode" class="rail-toolbar"><label class="check"><input type="checkbox" :checked="conversations.length > 0 && selectedConversationIds.length === conversations.length" @change="toggleAllConversations" /> 全选当前页</label><span class="selection-count">已选 {{ selectedConversationIds.length }} 项</span><button v-if="!showDeleted" class="button danger" :disabled="!selectedConversationIds.length || sending || loadingMessages || !!deletingId" @click="deleteSelectedConversations">{{ deletingId === 'bulk' ? '删除中…' : `删除选中（${selectedConversationIds.length}）` }}</button></div>
        <div class="rail-switch"><button type="button" :class="{ active: !showDeleted }" @click="switchDeletedView(false)">正常会话</button><button type="button" :class="{ active: showDeleted }" @click="switchDeletedView(true)">已删除</button></div>
        <div class="conversation-scroll">
        <div v-if="loadingList && !conversations.length" class="rail-state">正在加载会话…</div>
        <div v-else-if="!conversations.length" class="rail-state">暂无历史会话<br />从右侧输入问题开始。</div>
        <div v-for="item in conversations" :key="item.id" :class="['conversation-item', { active: activeId === item.id }]">
          <input v-if="managementMode" class="conversation-check" type="checkbox" :checked="selectedConversationIds.includes(item.id)" :aria-label="`选择会话：${item.title}`" @change="toggleConversationSelection(item.id)" />
          <button v-if="!showDeleted || !managementMode" class="conversation-select" :disabled="sending || loadingMessages || deletingId === item.id || showDeleted" @click="selectConversation(item.id)">
            <strong>{{ item.title }}</strong><time>{{ new Date(item.updated_at).toLocaleString('zh-CN', { hour12: false }) }}</time>
          </button>
          <div v-if="showDeleted && managementMode" class="deleted-actions"><button type="button" @click="restoreDeletedConversation(item)">恢复</button><button type="button" @click="permanentlyRemoveConversation(item)">永久删除</button></div>
        </div>
        <button v-if="canLoadMore" class="load-more" :disabled="loadingList" @click="loadConversationList(false)">{{ loadingList ? '加载中…' : '加载更多' }}</button>
        </div>
        <footer class="conversation-actions">
          <button class="button" :disabled="sending || loadingMessages || loadingList" @click="refreshConversations">刷新会话</button>
          <button class="button" :disabled="sending || loadingMessages" @click="newConversation">新增会话</button>
        </footer>
      </aside>

      <section class="dialogue-panel panel">
        <header class="dialogue-head"><div><span>{{ activeConversation ? '当前会话' : '新会话' }}</span><strong>{{ activeConversation?.title ?? '提出一个可核验的产品问题' }}</strong></div><div class="dialogue-actions"><button class="button" type="button" @click="showUsageGuide = true">使用说明</button><button class="button" type="button" @click="evidenceVisible = !evidenceVisible">{{ evidenceVisible ? '收起证据' : '展开证据' }}</button></div></header>
        <div ref="messageScroller" class="message-scroll" aria-live="polite" :aria-busy="loadingMessages || sending" @scroll="updateScrollState">
          <div v-if="loadingMessages" class="loading-state">正在读取会话历史…</div>
          <section v-else-if="showUsageGuide && !pendingQuestion" class="usage-guide" aria-labelledby="usage-guide-title">
            <header><div><span class="welcome-code">{{ capabilitySnapshot.version }} / 使用说明</span><h2 id="usage-guide-title">先确认资料边界，再使用回答</h2></div><button v-if="messages.length" type="button" class="guide-close" aria-label="关闭使用说明" @click="showUsageGuide = false">×</button></header>
            <p class="guide-status"><strong>{{ capabilitySnapshot.status }}</strong>{{ capabilitySnapshot.note }}</p>
            <div class="guide-section">
              <h3>主要功能</h3>
              <p v-if="!confirmedStableCapabilities.length" class="guide-empty">暂无经人工确认的稳定能力，不用候选能力凑数。</p>
              <article v-for="item in confirmedStableCapabilities.slice(0, 3)" :key="item.name" class="guide-card">
                <h4>{{ item.name }}</h4><p>{{ item.description }}</p>
                <button v-for="question in item.examples.slice(0, 2)" :key="question" type="button" class="example" @click="fillExample(question)">{{ question }}</button>
              </article>
            </div>
            <div class="guide-section candidate-section"><h3>稳定能力候选</h3><p v-if="!candidateCapabilities.length" class="guide-empty">本轮没有能力达到稳定门槛。</p><ul v-else><li v-for="item in candidateCapabilities" :key="item.name"><strong>{{ item.name }}</strong><span>{{ item.description }}</span></li></ul></div>
            <div class="guide-section"><h3>使用条件</h3><article v-for="item in usageConditions" :key="item.name" class="notice-row"><strong>{{ item.name }}</strong><p>{{ item.description }}</p></article></div>
            <div class="guide-section"><h3>资料覆盖范围</h3><article v-for="item in materialBoundaries" :key="item.name" class="notice-row"><strong>{{ item.name }}</strong><p>{{ item.description }}</p></article></div>
            <div class="guide-section"><h3>已验证问题</h3><article v-for="item in verifiedIssues" :key="item.name" class="notice-row"><strong>{{ item.name }}</strong><p>{{ item.description }}</p></article></div>
          </section>
          <div v-else-if="!messages.length && !pendingQuestion" class="welcome-state"><span class="welcome-code">Q / A</span><h2>从问题开始，沿证据链验证结论</h2><p>资料不足时会说明边界并追问；确定性查价和预算计算仍由后端完成。</p><div><button class="example" type="button" @click="showUsageGuide = true">查看使用说明</button></div></div>
          <template v-else>
            <AgentMessage v-for="item in messages" :key="item.id" :message="item" :selected="selectedMessageId === item.id" @click="item.role === 'ASSISTANT' && (selectedMessageId = item.id)" @citation-select="ref => selectCitation(item.id, ref)" />
            <article v-if="pendingQuestion" class="pending-message"><div><span>问题</span><p>{{ pendingQuestion }}</p></div><strong>正在检索并组织证据</strong></article>
          </template>
          <button v-if="showLatest" class="latest-button" type="button" @click="scrollToLatest">查看最新</button>
        </div>
        <form class="composer" @submit.prevent="submit">
          <label class="prompt-field"><span class="sr-only">产品分析问题</span><textarea v-model="draft.message" maxlength="2000" rows="3" placeholder="输入产品问题；Enter 发送，Shift+Enter 换行" :disabled="sending" @keydown="keydown" /><small class="numeric">{{ draft.message.length }} / 2000</small></label>
          <button class="button primary send-button" :disabled="sending || loadingMessages || !draft.message.trim()">{{ sending ? '正在检索并组织证据' : '发送问题' }}</button>
        </form>
      </section>

      <aside v-if="evidenceVisible" class="evidence-rail panel" aria-label="回答证据与工具记录">
        <div class="evidence-head"><span>证据链</span><small>{{ selectedEvidence ? '当前选中回答' : '等待回答' }}</small></div>
        <div class="evidence-scroll"><CitationList :citations="selectedEvidence?.citations ?? []" :message-id="selectedEvidence?.id" :highlighted-ref="highlightedCitationRef" /><ToolCallList :tools="selectedEvidence?.tool_summary ?? []" /></div>
      </aside>
    </div>
    </div>
  </section>
</template>

<style scoped>
.agent-page { min-width: 0; }
.agent-stage { height: calc(100dvh - var(--topbar-height) - 56px); min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.agent-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.agent-heading h1 { margin: 3px 0; font-size: 26px; }
.agent-heading p { margin: 0; color: var(--color-text-secondary); font-size: 12px; }
.agent-workbench { flex: 1; min-height: 0; display: grid; grid-template-columns: clamp(200px, 18vw, 240px) minmax(0, 1fr) clamp(260px, 24vw, 320px); gap: 12px; overflow-x: auto; }
.agent-workbench.evidence-hidden { grid-template-columns: clamp(200px, 18vw, 240px) minmax(0, 1fr); }
.conversation-rail, .evidence-rail, .dialogue-panel { min-height: 0; overflow: hidden; }
.conversation-rail { display: flex; flex-direction: column; padding: 8px; }
.conversation-scroll { flex: 1; min-height: 0; overflow-y: auto; }
.conversation-actions { flex-shrink: 0; display: flex; gap: 8px; padding: 10px 0 0; border-top: 1px solid var(--color-border-soft); }
.conversation-actions .button { flex: 1; }
.rail-head, .evidence-head { display: flex; align-items: center; justify-content: space-between; min-height: 44px; padding: 0 10px; border-bottom: 1px solid var(--color-border-soft); color: var(--color-text-secondary); font-size: 11px; font-weight: 700; letter-spacing: .6px; }
.conversation-item { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; width: 100%; border-bottom: 1px solid var(--color-border-soft); }
.conversation-item:hover { background: var(--color-surface-subtle); }
.conversation-item.active { border-radius: 8px; background: var(--color-accent-soft); color: var(--color-accent); }
.conversation-select { display: grid; gap: 5px; min-width: 0; padding: 11px 6px 11px 10px; border: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; }
.conversation-select strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.conversation-select time { color: var(--color-text-tertiary); font-size: 9px; font-variant-numeric: tabular-nums; }
.conversation-delete { margin-right: 6px; padding: 5px 6px; border: 0; border-radius: 5px; background: transparent; color: var(--color-text-tertiary); cursor: pointer; font-size: 10px; }
.conversation-delete:hover:not(:disabled), .conversation-delete:focus-visible { background: var(--color-danger-soft, #fee2e2); color: var(--color-danger, #b42318); }
.conversation-delete:disabled { cursor: wait; opacity: .6; }
.conversation-check { margin: 0 2px 0 8px; }
.rail-toolbar, .rail-switch { display: flex; align-items: center; gap: 7px; padding: 8px 6px; border-bottom: 1px solid var(--color-border-soft); }
.rail-toolbar { justify-content: space-between; flex-wrap: wrap; }
.rail-toolbar .button { min-height: 28px; padding: 5px 8px; font-size: 10px; }
.selection-count { color: var(--color-text-tertiary); font-size: 10px; }
.rail-switch button, .rail-manage { border: 0; background: transparent; color: var(--color-text-tertiary); cursor: pointer; font-size: 10px; }
.rail-switch button.active, .rail-manage { color: var(--color-accent); font-weight: 700; }
.deleted-actions { display: flex; gap: 4px; padding: 8px 5px; }
.deleted-actions button { border: 0; background: transparent; color: var(--color-accent); cursor: pointer; font-size: 10px; }
.deleted-actions button:last-child { color: var(--color-danger, #b42318); }
.rail-state { padding: 30px 12px; color: var(--color-text-tertiary); text-align: center; font-size: 11px; line-height: 1.7; }
.load-more { min-height: 34px; margin-top: 6px; border: 0; background: transparent; color: var(--color-accent); cursor: pointer; font-size: 11px; }
.dialogue-panel { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; }
.dialogue-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 58px; padding: 9px 14px; border-bottom: 1px solid var(--color-border-soft); }
.dialogue-head div { min-width: 0; }
.dialogue-head span, .dialogue-head strong { display: block; }
.dialogue-head span { color: var(--color-accent); font-size: 9px; font-weight: 700; letter-spacing: .8px; }
.dialogue-head strong { margin-top: 4px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.dialogue-actions { display: flex; flex-shrink: 0; gap: 7px; }
.dialogue-actions .button { min-height: 32px; padding: 6px 10px; }
.message-scroll { position: relative; display: flex; flex-direction: column; gap: 12px; min-height: 0; overflow-y: auto; padding: 16px; background: var(--color-surface-subtle); }
.latest-button { position: absolute; right: 14px; bottom: 12px; z-index: 2; padding: 7px 10px; border: 1px solid var(--color-accent); border-radius: 999px; background: var(--color-surface); color: var(--color-accent); box-shadow: var(--shadow-sm); cursor: pointer; font-size: 11px; }
.welcome-state { display: grid; place-items: center; align-content: center; min-height: 100%; padding: 24px; text-align: center; }
.welcome-code { color: var(--color-accent); font-size: 11px; font-weight: 800; letter-spacing: 2px; }
.welcome-state h2 { max-width: 440px; margin: 12px 0 7px; font-size: 21px; }
.welcome-state p { max-width: 480px; margin: 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.7; }
.welcome-state > div { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 20px; }
.example { padding: 8px 10px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface); color: var(--color-accent); cursor: pointer; font-size: 11px; }
.usage-guide { width: min(100%, 760px); margin: auto; padding: 22px; border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-surface); box-shadow: var(--shadow-sm); }
.usage-guide > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.usage-guide h2 { margin: 7px 0 0; font-size: 20px; }
.guide-close { border: 0; background: transparent; color: var(--color-text-tertiary); cursor: pointer; font-size: 24px; line-height: 1; }
.guide-status { display: grid; grid-template-columns: auto 1fr; gap: 10px; margin: 14px 0; padding: 10px 12px; border-radius: 8px; background: var(--color-accent-soft); color: var(--color-text-secondary); font-size: 11px; line-height: 1.6; }
.guide-status strong { color: var(--color-accent); }
.guide-section { margin-top: 15px; }
.guide-section h3 { margin: 0 0 8px; color: var(--color-text-secondary); font-size: 11px; letter-spacing: .7px; }
.guide-empty { margin: 0; padding: 12px; border: 1px dashed var(--color-border); border-radius: 8px; color: var(--color-text-tertiary); font-size: 11px; }
.guide-card { padding: 12px; border: 1px solid var(--color-border-soft); border-radius: 8px; }
.guide-card h4, .guide-card p { margin: 0 0 7px; }
.candidate-section ul { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; padding: 0; list-style: none; }
.candidate-section li { display: grid; gap: 5px; padding: 10px; border-radius: 8px; background: var(--color-surface-subtle); font-size: 10px; line-height: 1.5; }
.candidate-section li span { color: var(--color-text-secondary); }
.notice-row { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 3px 12px; padding: 9px 0; border-top: 1px solid var(--color-border-soft); font-size: 10px; line-height: 1.5; }
.notice-row p { margin: 0; color: var(--color-text-secondary); }
.notice-row small { grid-column: 2; color: var(--color-text-tertiary); }
.pending-message { display: flex; align-items: center; justify-content: space-between; gap: 14px; width: min(85%, 760px); margin-left: auto; padding: 13px 15px; border: 1px solid var(--color-accent); border-radius: 10px; background: var(--color-accent-soft); }
.pending-message span { color: var(--color-accent); font-size: 9px; font-weight: 700; }
.pending-message p { margin: 5px 0 0; font-size: 12px; white-space: pre-wrap; }
.pending-message strong { color: var(--color-accent); font-size: 11px; white-space: nowrap; }
.composer { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 9px; padding: 12px; border-top: 1px solid var(--color-border); background: var(--color-surface); }
.prompt-field { position: relative; }
.prompt-field textarea { width: 100%; min-height: 72px; resize: none; padding: 10px 54px 10px 11px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-inset); color: var(--color-text-primary); font-size: 12px; line-height: 1.55; }
.prompt-field textarea:focus { border-color: var(--color-accent); background: var(--color-surface); box-shadow: 0 0 0 3px var(--color-accent-soft); }
.prompt-field small { position: absolute; right: 9px; bottom: 8px; color: var(--color-text-muted); font-size: 9px; }
.send-button { align-self: stretch; min-width: 106px; }
.evidence-rail { position: sticky; top: calc(var(--topbar-height) + 12px); display: grid; grid-template-rows: auto minmax(0, 1fr); max-height: calc(100vh - var(--topbar-height) - 24px); }
.evidence-head small { color: var(--color-text-tertiary); font-size: 9px; font-weight: 500; }
.evidence-scroll { min-height: 0; overflow-y: auto; padding: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 1390px) {
  .agent-workbench { grid-template-columns: 220px minmax(400px, 1fr) 280px; }
  .agent-workbench.evidence-hidden { grid-template-columns: 220px minmax(400px, 1fr); }
}

/* C｜文档情报：将工作区处理成“深紫画布 + 暖白纸张面板”，不改变交互结构。 */
.agent-page { color: var(--color-text-primary); }
.agent-heading { animation: agent-heading-in 360ms cubic-bezier(.22, 1, .36, 1) both; }
.agent-heading h1 {
  color: var(--color-surface);
  font-family: var(--font-serif);
  font-size: clamp(26px, 2.4vw, 34px);
  letter-spacing: .01em;
}
.agent-heading p { color: rgba(242, 236, 226, .72); }
.agent-heading .kicker { color: rgba(242, 236, 226, .78); }
.agent-workbench { gap: 14px; }
.agent-workbench > .panel {
  border-color: rgba(242, 236, 226, .34);
  border-radius: 16px;
  box-shadow: 0 14px 32px rgba(11, 10, 10, .24);
  animation: workbench-panel-in 420ms cubic-bezier(.22, 1, .36, 1) both;
}
.agent-workbench > .panel:nth-child(1) { animation-delay: 40ms; }
.agent-workbench > .panel:nth-child(2) { animation-delay: 90ms; }
.agent-workbench > .panel:nth-child(3) { animation-delay: 140ms; }
.conversation-rail, .dialogue-panel, .evidence-rail { position: relative; }
.conversation-rail::before, .dialogue-panel::before, .evidence-rail::before {
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  content: '';
  background: var(--color-accent);
  opacity: .58;
}
.dialogue-panel::before { opacity: .18; }
.evidence-rail::before { opacity: .34; }
.rail-head, .evidence-head { color: var(--color-text-primary); }
.rail-head span, .evidence-head span { font-family: var(--font-serif); font-size: 13px; }
.rail-manage, .rail-switch button, .deleted-actions button { transition: color 180ms ease, background-color 180ms ease, transform 180ms ease; }
.rail-manage:hover, .rail-switch button:hover, .deleted-actions button:hover { color: var(--color-accent); transform: translateX(2px); }
.rail-switch button.active {
  border-left: 2px solid var(--color-accent);
  border-radius: 4px;
  background: #e7dbd1;
  color: var(--color-accent);
}
.conversation-item {
  border-bottom-color: var(--color-border-soft);
  transition: background-color 180ms ease, border-color 180ms ease, transform 180ms ease;
}
.conversation-item:hover { background: #ece2d8; transform: translateX(2px); }
.conversation-item.active { background: #e7dbd1; box-shadow: inset 3px 0 0 var(--color-accent); }
.conversation-select strong { font-family: var(--font-serif); }
.conversation-actions { background: rgba(242, 236, 226, .58); }
.dialogue-head { background: rgba(242, 236, 226, .92); }
.dialogue-head span { color: var(--color-accent); }
.dialogue-head strong { font-family: var(--font-serif); font-size: 14px; }
.dialogue-actions .button, .example, .latest-button {
  transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}
.dialogue-actions .button:hover, .example:hover, .latest-button:hover { transform: translateY(-2px); box-shadow: 0 7px 16px rgba(42, 31, 53, .14); }
.message-scroll { background: #e9dfd5; }
.usage-guide { background: #f7f0e7; box-shadow: 0 8px 24px rgba(42, 31, 53, .1); }
.usage-guide h2, .welcome-state h2 { font-family: var(--font-serif); }
.guide-status { background: var(--color-accent-soft); }
.guide-status strong, .guide-section h3 { color: var(--color-accent); }
.guide-card, .guide-empty, .notice-row { border-color: var(--color-border); }
.candidate-section li { background: #eee4da; }
.composer { background: rgba(242, 236, 226, .98); }
.prompt-field textarea { background: #e8ded3; }
.prompt-field textarea:focus { background: #fbf5ec; }
.send-button { min-width: 112px; background: var(--color-accent); }
.send-button:hover { background: var(--color-accent-hover); }
.evidence-rail {
  position: relative;
  top: auto;
  max-height: none;
  background: #f2ece2;
}
.evidence-scroll { background: #eee4da; }
.evidence-scroll :deep(.citation-item), .evidence-scroll :deep(.tool-list article) {
  border-color: var(--color-border);
  background: #f7f0e7;
  transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
}
.evidence-scroll :deep(.citation-item:hover), .evidence-scroll :deep(.tool-list article:hover) { transform: translateY(-2px); }
.evidence-scroll :deep(.citation-item.highlighted) {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
  animation: citation-focus 650ms ease-out 1;
}
.evidence-scroll :deep(.citation-index) { background: var(--color-accent-soft); color: var(--color-accent); }
.evidence-scroll :deep(.state.accent) { background: var(--color-accent-soft); color: var(--color-accent); }
.evidence-scroll :deep(.state.success) { background: var(--color-success-soft); color: var(--color-success); }

@keyframes agent-heading-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes workbench-panel-in {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes citation-focus {
  0% { transform: translateY(4px); box-shadow: 0 0 0 0 rgba(125, 48, 59, .1); }
  100% { transform: translateY(0); box-shadow: 0 0 0 3px var(--color-accent-soft); }
}

@media (prefers-reduced-motion: reduce) {
  .agent-heading, .agent-workbench > .panel { animation: none; }
  .conversation-item:hover, .dialogue-actions .button:hover, .example:hover, .latest-button:hover, .rail-manage:hover, .rail-switch button:hover, .deleted-actions button:hover, .evidence-scroll :deep(.citation-item:hover), .evidence-scroll :deep(.tool-list article:hover) { transform: none; }
  .evidence-scroll :deep(.citation-item.highlighted) { animation: none; }
}
</style>
