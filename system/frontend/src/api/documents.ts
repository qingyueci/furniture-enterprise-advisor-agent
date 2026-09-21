import http, { type ApiSuccess } from './http'
import type { Role } from './auth'

export type FileType = 'PDF' | 'DOCX' | 'XLSX'
export type ParseStatus = 'UPLOADING' | 'PARSING' | 'READY' | 'FAILED'
export type SecurityLevel = 'PUBLIC' | 'INTERNAL' | 'RESTRICTED'

export interface DocumentItem {
  id: string
  document_name: string
  original_name: string
  file_type: FileType
  file_size: number
  security_level: SecurityLevel
  parse_status: ParseStatus
  parse_error: string | null
  upload_user_id: string
  product_ids: number[]
  allowed_roles: Role[] | null
  created_at: string
  updated_at: string
}

export interface DocumentListData {
  items: DocumentItem[]
  pagination: { page: number; page_size: number; total: number }
}

export interface DocumentFilters {
  keyword?: string
  file_type?: FileType
  parse_status?: ParseStatus
  product_id?: number
  page?: number
  page_size?: number
}

export async function fetchDocuments(filters: DocumentFilters = {}): Promise<DocumentListData> {
  const { data } = await http.get<ApiSuccess<DocumentListData>>('/documents', { params: filters })
  return data.data
}

export async function uploadDocument(payload: {
  file: File
  document_name: string
  security_level: SecurityLevel
  allowed_roles: Role[]
  product_ids: number[]
}): Promise<{ document_id: string; file_type: FileType; parse_status: 'PARSING' }> {
  const form = new FormData()
  form.append('file', payload.file)
  form.append('document_name', payload.document_name)
  form.append('security_level', payload.security_level)
  payload.allowed_roles.forEach(role => form.append('allowed_roles', role))
  payload.product_ids.forEach(id => form.append('product_ids', String(id)))
  const { data } = await http.post<ApiSuccess<{ document_id: string; file_type: FileType; parse_status: 'PARSING' }>>('/documents/upload', form)
  return data.data
}

export async function updateDocumentPermissions(id: string, payload: { security_level: SecurityLevel; allowed_roles: Role[] }): Promise<DocumentItem> {
  const { data } = await http.put<ApiSuccess<DocumentItem>>(`/documents/${id}/permissions`, payload)
  return data.data
}

export async function downloadDocument(item: DocumentItem): Promise<void> {
  const response = await http.get<Blob>(`/documents/${item.id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = item.original_name
  link.click()
  URL.revokeObjectURL(url)
}

export async function deleteDocument(id: string): Promise<void> {
  await http.delete(`/documents/${id}`)
}
