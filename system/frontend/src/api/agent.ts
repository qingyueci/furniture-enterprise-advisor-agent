/**
 * Agent/产品比较共享类型。
 *
 * 本文件声明阶段 6/7 后端 API 对应的 TypeScript 类型与阶段 10 请求函数。
 * 金额沿用后端 JSON 的两位小数字符串。
 */

import axios from 'axios'
import http, { type ApiSuccess } from './http'

export type MoneyString = string
export type TaskType =
  | 'KNOWLEDGE_QUERY'
  | 'DOCUMENT_READ'
  | 'PRICE_QUERY'
  | 'PRODUCT_COMPARE'
  | 'PRODUCT_RECOMMENDATION'
  | 'CONSULTATION'
  | 'UNSUPPORTED'

export type PriceType = 'GUIDE' | 'SALES' | 'INTERNAL_QUOTE'
export type ToolStatus = 'SUCCESS' | 'PARTIAL' | 'FAILED' | 'DENIED'
export type ToolName =
  | 'search_product_knowledge'
  | 'read_document'
  | 'query_product_price'
  | 'compare_products'
export type ComparisonStatus = 'AVAILABLE' | 'MISSING' | 'CONFLICT'
export type CitationSourceType = 'DOCUMENT' | 'PRICE' | 'PRODUCT'

export interface ProductSummary {
  product_id: number | null
  product_name: string
  model: string | null
  brand: string | null
  product_type: string | null
  summary: string | null
  source_refs: string[]
}

export interface PriceCard {
  quote_spec?: string | null
  pricing_unit?: string | null
  included_scope?: string | null
  product_id: number | null
  product_name: string
  /** null means the stable display text “暂无价格”. */
  price: MoneyString | null
  currency: string
  price_type: PriceType
  source: string | null
  update_time: string | null
  status: ComparisonStatus
  /** Derived display value: “暂无价格” when price is null. */
  display_price: string
}

export interface Citation {
  ref: string | null
  source_type: CitationSourceType
  document_id: string | null
  chunk_id: string | null
  document_name: string | null
  page_start: number | null
  page_end: number | null
  section_title: string | null
  row_start: number | null
  row_end: number | null
  price_id: number | null
  product_id: number | null
  source: string | null
  quote: string | null
  evidence_category: string | null
  worksheet: string | null
  record_id: string | null
  source_id: string | null
  usage_restriction: string | null
}

export interface ComparisonRow {
  dimension: string
  /** Always two entries, aligned with ProductComparisonData.products. */
  values: string[]
  source_refs: string[]
  status: ComparisonStatus
  note: string | null
}

export interface BudgetCheck {
  budget: MoneyString
  within_budget: [boolean | null, boolean | null]
  currency: string
  reasons: [string, string]
  over_budget_amounts: [MoneyString | null, MoneyString | null]
  /** price A - price B; positive means A is more expensive. */
  price_difference: MoneyString | null
  price_difference_reason: string | null
}

export interface ConditionalRecommendation {
  recommended_product: string | null
  condition: string
  rationale: string | null
  source_refs: string[]
}

export interface MissingInformation {
  field: string
  message: string
  status: ComparisonStatus
  source_refs: string[]
}

export interface EvidenceClaim {
  text: string
  source_refs: string[]
}

export interface ProductComparisonData {
  kind: 'PRODUCT_COMPARISON'
  /** Exactly two product names. No aggregate score is part of the contract. */
  products: [string, string]
  summaries: ProductSummary[]
  price_cards: PriceCard[]
  rows: ComparisonRow[]
  budget_check: BudgetCheck | null
  advantages: Record<string, EvidenceClaim[]>
  limitations: Record<string, EvidenceClaim[]>
  missing_fields: MissingInformation[]
  citations: Citation[]
  recommendation: ConditionalRecommendation | null
  overall_status: ToolStatus
}

export interface PriceQueryData {
  kind: 'PRICE_QUERY'
  price_cards: [PriceCard]
}

/**
 * 后端 ConsultationData 的跨轮状态字段。
 *
 * 这些结构只用于准确表达响应内容，前端不从本地上传，也不新增状态管理：
 * 会话状态始终由后端从最近一条助手消息恢复。
 */
export interface PendingSlot {
  name: string
  /** 已知取值：'number' | 'choice'；后端保留扩展可能。 */
  value_type: 'number' | 'choice' | string
  unit?: string
  object?: string
  options?: string[]
  ask_text?: string
  visible?: boolean
}

export interface SessionCondition {
  object?: string
  name: string
  value: string | number
  unit?: string
  source?: string
  original_reply?: string
}

export interface ConsultationData {
  kind: 'CONSULTATION'
  answer_format: 'CANDIDATES' | 'COMPARISON_TABLE' | 'QUOTE_BREAKDOWN' | 'CHECKLIST'
  retrieval_queries: string[]
  degraded: boolean
  pending_slots: PendingSlot[]
  conversation_topic: string | null
  session_conditions: SessionCondition[]
}

export interface ToolCallSummary {
  tool: string
  status: ToolStatus
  duration_ms: number
}

export interface AgentChatData {
  conversation_id: string
  message_id: string
  task_type: TaskType
  answer: string
  structured_data: PriceQueryData | ProductComparisonData | ConsultationData | null
  citations: Citation[]
  tool_calls: ToolCallSummary[]
  missing_information: string[]
  warnings: string[]
}

export interface AgentChatRequest {
  conversation_id?: string
  message: string
  selected_product_ids?: number[]
  selected_document_id?: string
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string
}

export interface ConversationMessage {
  id: string
  role: 'USER' | 'ASSISTANT'
  content: string
  task_type: TaskType | null
  structured_data: PriceQueryData | ProductComparisonData | ConsultationData | null
  citations: Citation[]
  tool_summary: ToolCallSummary[]
  /** Stable warning codes persisted per message; always empty for USER messages. */
  warnings: string[]
  created_at: string
}

export interface ConversationData {
  id: string
  title: string
  messages: ConversationMessage[]
  pagination: { page: number; page_size: number; total: number }
  created_at: string
  updated_at: string
}

export interface ConversationListData {
  items: ConversationSummary[]
  pagination: { page: number; page_size: number; total: number }
}

// 兼容后续组件较短的命名；类型保持同一份结构。
export type ChatResponse = AgentChatData
export type ComparisonOutput = ProductComparisonData
export type PriceCardData = PriceCard
export type CitationData = Citation
export type BudgetJudgement = BudgetCheck
export type Recommendation = ConditionalRecommendation

const agentHttp = axios.create({ baseURL: '/api', timeout: 70000 })
agentHttp.interceptors.request.use(config => {
  const token = sessionStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
agentHttp.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401) window.dispatchEvent(new Event('auth:expired'))
  return Promise.reject(error)
})

export async function sendAgentMessage(payload: AgentChatRequest): Promise<AgentChatData> {
  const { data } = await agentHttp.post<ApiSuccess<AgentChatData>>('/agent/chat', payload)
  return data.data
}

export async function fetchConversations(page = 1, pageSize = 20): Promise<ConversationListData> {
  const { data } = await http.get<ApiSuccess<ConversationListData>>('/conversations', { params: { page, page_size: pageSize } })
  return data.data
}

export async function fetchConversation(id: string, page = 1, pageSize = 50): Promise<ConversationData> {
  const { data } = await http.get<ApiSuccess<ConversationData>>(`/conversations/${id}`, { params: { page, page_size: pageSize } })
  return data.data
}

export async function fetchDeletedConversations(page = 1, pageSize = 20): Promise<ConversationListData> {
  const { data } = await http.get<ApiSuccess<ConversationListData>>('/conversations', { params: { page, page_size: pageSize, include_deleted: true } })
  return data.data
}

export async function deleteConversation(id: string): Promise<void> {
  await http.delete(`/conversations/${id}`)
}

export async function deleteConversations(ids: string[]): Promise<void> {
  await http.post('/conversations/bulk-delete', { ids })
}

export async function restoreConversation(id: string): Promise<void> {
  await http.post(`/conversations/${id}/restore`)
}

export async function permanentlyDeleteConversation(id: string): Promise<void> {
  await http.delete(`/conversations/${id}/permanent`)
}
