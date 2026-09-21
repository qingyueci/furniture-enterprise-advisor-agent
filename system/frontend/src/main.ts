import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import 'element-plus/dist/index.css'
import './styles/theme.css'

const pinia = createPinia()
const app = createApp(App).use(pinia).use(router)
let expiryRedirecting = false
const onAuthExpired = async () => {
  const current = router.currentRoute.value
  useAuthStore(pinia).clear()
  if (current.path === '/login' || expiryRedirecting) return
  expiryRedirecting = true
  try { await router.replace({ path: '/login', query: { redirect: current.fullPath } }) }
  finally { expiryRedirecting = false }
}
window.addEventListener('auth:expired', onAuthExpired)
window.addEventListener('beforeunload', () => window.removeEventListener('auth:expired', onAuthExpired), { once: true })
if (import.meta.hot) import.meta.hot.dispose(() => window.removeEventListener('auth:expired', onAuthExpired))
app.mount('#app')
