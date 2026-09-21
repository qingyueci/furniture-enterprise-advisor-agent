import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import AppShell from '../components/AppShell.vue'
import AgentView from '../views/AgentView.vue'
import UserManagementView from '../views/UserManagementView.vue'
import ProductsView from '../views/ProductsView.vue'
import DocumentsView from '../views/DocumentsView.vue'
import AuditLogsView from '../views/AuditLogsView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { guest: true } },
    { path: '/', redirect: '/agent' },
    { path: '/', component: AppShell, meta: { protected: true }, children: [
      { path: 'agent', component: AgentView },
      { path: 'styles', component: () => import('../views/StyleGuideView.vue') },
      { path: 'products', component: ProductsView },
      { path: 'documents', component: DocumentsView, meta: { admin: true } },
      { path: 'users', component: UserManagementView, meta: { admin: true } },
      { path: 'audit-logs', component: AuditLogsView, meta: { admin: true } },
    ] },
    { path: '/:pathMatch(.*)*', redirect: '/agent' },
  ],
})

router.beforeEach(async to => {
  const auth = useAuthStore()
  await auth.restore()
  if (to.matched.some(record => record.meta.protected) && !auth.user) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.guest && auth.user) return '/agent'
  if (to.matched.some(record => record.meta.admin) && !auth.isAdmin) return '/agent'
  return true
})

export default router
