import axios from 'axios'

export interface ApiErrorPayload {
  success: false
  error: { code: string; message: string; details: null }
  request_id: string
}

export interface ApiSuccess<T> {
  success: true
  data: T
  request_id: string
}

const http = axios.create({ baseURL: '/api', timeout: 10000 })

http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) window.dispatchEvent(new Event('auth:expired'))
    return Promise.reject(error)
  },
)

export function messageFor(error: unknown, fallback = '请求未完成，请稍后重试。'): string {
  if (axios.isAxiosError<ApiErrorPayload>(error)) return error.response?.data?.error?.message ?? fallback
  return fallback
}

export default http
