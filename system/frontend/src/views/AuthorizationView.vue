<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
async function signOut() { await auth.logout(); await router.replace('/login') }
</script>

<template>
  <main class="shell">
    <header><span class="mark">PA / 04</span><nav><RouterLink to="/products">产品价格</RouterLink><RouterLink v-if="auth.isAdmin" to="/documents">资料管理</RouterLink><RouterLink v-if="auth.isAdmin" to="/users">用户管理</RouterLink><button @click="signOut">退出登录</button></nav></header>
    <section>
      <p class="eyebrow">认证状态</p>
      <h1>当前用户</h1>
      <div class="panel">
        <div><span>用户名</span><strong>{{ auth.user?.username }}</strong></div>
        <div><span>角色</span><strong>{{ auth.user?.role }}</strong></div>
        <div><span>登录状态</span><strong class="ok">已认证 · {{ auth.user?.status }}</strong></div>
      </div>
      <div class="capabilities"><h2>当前已完成</h2><ul><li>用户名密码登录、JWT Access Token 与三角色 RBAC</li><li>产品列表、详情与结构化演示价格查询</li><li>企业产品资料安全上传、授权下载与管理</li></ul></div>
      <RouterLink class="primary link" to="/products">进入产品价格查询</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.shell { max-width: 880px; margin: 0 auto; padding: 32px 28px 64px; }header { display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid #dce4df; padding-bottom:24px; }.mark,.eyebrow { color:#245b4d; font-size:12px; font-weight:700; letter-spacing:2px; }nav { display:flex; align-items:center; gap:16px; }nav a,nav button { color:#245b4d; background:transparent; border:0; font:inherit; font-size:13px; cursor:pointer; text-decoration:none; }section { margin-top:64px; }h1 { font-size:32px; margin:12px 0 26px; } .panel { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid #dce4df; border-radius:10px; background:#fff; }.panel div { padding:22px; border-right:1px solid #eef1ef; }.panel div:last-child { border:0; }.panel span { display:block; color:#6c7b74; font-size:12px; margin-bottom:8px; }.panel strong { font-size:15px; word-break:break-word; }.ok { color:#1a6e4e; }.capabilities { margin-top:30px; }.capabilities h2 { font-size:17px; }.capabilities li { margin:10px 0; color:#44534d; font-size:14px; }.primary { display:inline-block; margin-top:20px; padding:11px 16px; border-radius:7px; background:#245b4d; color:#fff; font-weight:600; text-decoration:none; font-size:14px; }@media(max-width:600px){.shell{padding:24px 18px}.panel{grid-template-columns:1fr}.panel div{border-right:0;border-bottom:1px solid #eef1ef}.panel div:last-child{border-bottom:0}section{margin-top:40px}}
</style>
