import http, { type ApiSuccess } from './http'
import type { CurrentUser, Role, UserStatus } from './auth'

export interface UserListData {
  items: CurrentUser[]
  pagination: { page: number; page_size: number; total: number }
}

export interface UserFilters { keyword?: string; role?: Role; status?: UserStatus; include_deleted?: boolean; page?: number; page_size?: number }
export interface CreateUser { username: string; password: string; role: Role; status: UserStatus }
export interface UpdateUser { username?: string; role?: Role; status?: UserStatus; new_password?: string }

export async function fetchUsers(filters: UserFilters = {}): Promise<UserListData> {
  const { data } = await http.get<ApiSuccess<UserListData>>('/users', { params: filters })
  return data.data
}

export async function createUser(payload: CreateUser): Promise<CurrentUser> {
  const { data } = await http.post<ApiSuccess<CurrentUser>>('/users', payload)
  return data.data
}

export async function updateUser(id: string, payload: UpdateUser): Promise<CurrentUser> {
  const { data } = await http.put<ApiSuccess<CurrentUser>>(`/users/${id}`, payload)
  return data.data
}

export async function deleteUser(id: string): Promise<void> { await http.delete(`/users/${id}`) }
export async function deleteUsers(ids: string[]): Promise<void> { await http.post('/users/bulk-delete', { ids }) }
export async function restoreUser(id: string): Promise<CurrentUser> { const { data } = await http.post<ApiSuccess<CurrentUser>>(`/users/${id}/restore`); return data.data }
export async function permanentlyDeleteUser(id: string): Promise<void> { await http.delete(`/users/${id}/permanent`) }
