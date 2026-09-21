import http, { type ApiSuccess } from './http'

export type Role = 'ADMIN' | 'PRODUCT_MANAGER' | 'SALES'
export type UserStatus = 'ACTIVE' | 'DISABLED'

export interface CurrentUser {
  id: string
  username: string
  role: Role
  status: UserStatus
  created_at: string
}

export interface LoginData {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: CurrentUser
}

export async function login(username: string, password: string): Promise<LoginData> {
  const { data } = await http.post<ApiSuccess<LoginData>>('/auth/login', { username, password })
  return data.data
}

export async function getMe(): Promise<CurrentUser> {
  const { data } = await http.get<ApiSuccess<CurrentUser>>('/auth/me')
  return data.data
}

export async function logout(): Promise<void> {
  await http.post('/auth/logout')
}
