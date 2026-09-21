import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '../api/auth'

const TOKEN_KEY = 'access_token'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<authApi.CurrentUser | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const isAdmin = computed(() => user.value?.role === 'ADMIN')

  function clear() {
    sessionStorage.removeItem(TOKEN_KEY)
    user.value = null
    initialized.value = true
  }

  async function restore() {
    if (initialized.value) return
    if (!sessionStorage.getItem(TOKEN_KEY)) { initialized.value = true; return }
    try { user.value = await authApi.getMe() }
    catch { sessionStorage.removeItem(TOKEN_KEY); user.value = null }
    finally { initialized.value = true }
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const result = await authApi.login(username, password)
      sessionStorage.setItem(TOKEN_KEY, result.access_token)
      user.value = result.user
      initialized.value = true
    } finally { loading.value = false }
  }

  async function logout() {
    try { await authApi.logout() } catch { return }
    finally { clear() }
  }

  return { user, initialized, loading, isAdmin, clear, restore, login, logout }
})
