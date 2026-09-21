/** 审计只读查询的共享类型与管理员查询函数；不创建展示页面。 */

import http, { type ApiSuccess } from './http'

export type AuditAction =
  | 'LOGIN_SUCCESS'
  | 'LOGIN_FAILED'
  | 'LOGOUT'
  | 'USER_CREATE'
  | 'USER_UPDATE'
  | 'DOCUMENT_UPLOAD'
  | 'DOCUMENT_PARSE_SUCCESS'
  | 'DOCUMENT_PARSE_FAILED'
  | 'DOCUMENT_PERMISSION_UPDATE'
  | 'DOCUMENT_DELETE'
  | 'DOCUMENT_READ'
  | 'PRODUCT_QUERY'
  | 'PRICE_QUERY'
  | 'AGENT_CHAT'
  | 'AGENT_TOOL_CALL'
  | 'PERMISSION_DENIED'

export type AuditResourceType = 'AUTH' | 'USER' | 'DOCUMENT' | 'PRODUCT' | 'PRICE' | 'AGENT'
export type AuditResult = 'SUCCESS' | 'FAILED' | 'DENIED'

export interface AuditDetail {
  error_code: string | null
  tool: string | null
  duration_ms: number | null
  request_id: string | null
  /** Backend-redacted note; never a prompt, token, path, or document body. */
  note: string | null
  /** Input alias accepted by the backend; API responses use note. */
  redacted_note?: string
}

export interface AuditLogItem {
  id: number
  user_id: string | null
  username: string | null
  action: AuditAction
  resource_type: AuditResourceType | null
  resource_id: string | null
  request_ip: string | null
  result: AuditResult
  detail: AuditDetail
  created_at: string
}

export interface AuditLogFilters {
  user_id?: string
  username?: string
  action?: AuditAction
  resource_type?: AuditResourceType
  result?: AuditResult
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}

export interface AuditLogListData {
  items: AuditLogItem[]
  pagination: { page: number; page_size: number; total: number }
}

export type AuditLog = AuditLogItem
export type AuditQuery = AuditLogFilters

export async function fetchAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogListData> {
  const { data } = await http.get<ApiSuccess<AuditLogListData>>('/audit-logs', { params: filters })
  return data.data
}
