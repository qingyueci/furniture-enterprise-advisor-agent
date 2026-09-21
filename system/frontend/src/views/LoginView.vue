<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { messageFor } from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const error = ref('')
const heroVideo = ref<HTMLVideoElement | null>(null)
let reducedMotion: MediaQueryList | null = null

function syncMotionPreference() {
  const video = heroVideo.value
  if (!video || !reducedMotion) return
  if (reducedMotion.matches) {
    video.pause()
    video.currentTime = 0
    return
  }
  void video.play().catch(() => undefined)
}

onMounted(() => {
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.addEventListener('change', syncMotionPreference)
  syncMotionPreference()
})

onBeforeUnmount(() => reducedMotion?.removeEventListener('change', syncMotionPreference))

async function submit() {
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/agent'
    await router.replace(redirect)
  } catch (exception) {
    error.value = messageFor(exception, '登录未完成，请稍后重试。')
  }
}
</script>

<template>
  <main class="login-shell">
    <video ref="heroVideo" class="login-film" autoplay muted loop playsinline preload="auto" aria-hidden="true" tabindex="-1">
      <source src="/assets/furniture/login-hero.mp4" type="video/mp4" />
    </video>

    <header class="login-brand" aria-label="产品分析顾问工作台">
      <strong>PA</strong>
      <span>Furniture Advisory Agent</span>
    </header>

    <section class="login-intro" aria-labelledby="project-title">
      <p class="intro-label">Evidence-led decision workspace</p>
      <h1 id="project-title">《多维度安全管控的家具企业顾问Agent系统设计》</h1>
      <p class="intro-copy">面向产品、销售与管理岗位的证据化家具顾问工作台。</p>
    </section>

    <section class="login-panel" aria-labelledby="login-title">
      <div class="panel-heading">
        <p>安全访问</p>
        <h2 id="login-title">登录工作台</h2>
        <span>使用本地初始化的演示账号进入系统。</span>
      </div>

      <form class="login-form" :aria-busy="auth.loading" @submit.prevent="submit">
        <label class="login-field" for="login-username">
          <span>用户名</span>
          <input
            id="login-username"
            v-model="username"
            name="username"
            autocomplete="username"
            required
            minlength="3"
            maxlength="50"
            placeholder="请输入用户名"
            :aria-describedby="error ? 'login-error' : undefined"
          />
        </label>

        <label class="login-field" for="login-password">
          <span>密码</span>
          <input
            id="login-password"
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
            minlength="8"
            maxlength="64"
            placeholder="请输入密码"
            :aria-describedby="error ? 'login-error' : undefined"
          />
        </label>

        <p v-if="error" id="login-error" class="login-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="auth.loading">
          {{ auth.loading ? '正在验证身份…' : '登录系统' }}
        </button>
      </form>

      <p class="session-note">登录凭证仅保存在当前浏览器会话中，退出或身份失效后自动清除。</p>
    </section>
  </main>
</template>

<style scoped>
.login-shell {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 430px);
  grid-template-rows: auto minmax(0, 1fr);
  gap: 40px clamp(48px, 7vw, 120px);
  min-height: 100vh;
  min-height: 100dvh;
  padding: clamp(24px, 3.2vw, 52px) clamp(24px, 4.6vw, 76px);
  overflow: hidden;
  background: #050505;
  color: #f7f6f2;
}

.login-shell::before {
  position: absolute;
  z-index: -1;
  inset: 0;
  content: '';
  background:
    linear-gradient(90deg, rgba(3, 3, 3, .62) 0%, rgba(3, 3, 3, .13) 52%, rgba(3, 3, 3, .56) 100%),
    linear-gradient(180deg, rgba(3, 3, 3, .38) 0%, transparent 38%, rgba(3, 3, 3, .76) 100%);
}

.login-film {
  position: absolute;
  z-index: -2;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  background: #050505;
  animation: film-reveal 1.4s cubic-bezier(.16, 1, .3, 1) both;
}

.login-brand {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 14px;
  width: max-content;
  text-transform: uppercase;
  animation: rise-in .72s .08s cubic-bezier(.16, 1, .3, 1) both;
}

.login-brand strong {
  color: #fff;
  font-size: 18px;
  font-weight: 750;
  letter-spacing: -.04em;
}

.login-brand span {
  padding-left: 14px;
  border-left: 1px solid rgba(255, 255, 255, .32);
  color: rgba(255, 255, 255, .72);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: .2em;
}

.login-intro {
  align-self: end;
  max-width: 790px;
  padding-bottom: clamp(8px, 2.4vh, 28px);
  text-shadow: 0 2px 26px rgba(0, 0, 0, .45);
  animation: rise-in .86s .18s cubic-bezier(.16, 1, .3, 1) both;
}

.intro-label {
  margin: 0 0 18px;
  color: rgba(255, 255, 255, .62);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: .22em;
  text-transform: uppercase;
}

.login-intro h1 {
  max-width: 760px;
  margin: 0;
  color: #fff;
  font-family: "STZhongsong", "Songti SC", "SimSun", serif;
  font-size: clamp(38px, 4.4vw, 70px);
  font-weight: 400;
  line-height: 1.12;
  letter-spacing: -.055em;
  text-wrap: balance;
}

.intro-copy {
  max-width: 520px;
  margin: 22px 0 0;
  color: rgba(255, 255, 255, .74);
  font-size: clamp(13px, 1.05vw, 15px);
  line-height: 1.7;
  text-wrap: pretty;
}

.login-panel {
  align-self: center;
  width: 100%;
  padding: clamp(28px, 3vw, 42px);
  border: 1px solid rgba(255, 255, 255, .14);
  border-radius: 16px;
  background: rgba(10, 10, 10, .74);
  box-shadow: 0 28px 90px rgba(0, 0, 0, .28);
  backdrop-filter: blur(22px) saturate(.82);
  -webkit-backdrop-filter: blur(22px) saturate(.82);
  animation: rise-in .86s .32s cubic-bezier(.16, 1, .3, 1) both;
}

.panel-heading p {
  margin: 0 0 14px;
  color: rgba(255, 255, 255, .56);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: .18em;
}

.panel-heading h2 {
  margin: 0;
  color: #fff;
  font-size: 30px;
  font-weight: 620;
  line-height: 1.18;
  letter-spacing: -.045em;
}

.panel-heading span {
  display: block;
  margin-top: 10px;
  color: rgba(255, 255, 255, .62);
  font-size: 12px;
  line-height: 1.65;
}

.login-form {
  display: grid;
  gap: 18px;
  margin-top: 30px;
}

.login-field {
  display: grid;
  gap: 9px;
  color: rgba(255, 255, 255, .78);
  font-size: 12px;
  font-weight: 600;
}

.login-field input {
  width: 100%;
  min-height: 50px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, .17);
  border-radius: 10px;
  background: rgba(255, 255, 255, .075);
  color: #fff;
  caret-color: #fff;
  transition: background-color 160ms, border-color 160ms, box-shadow 160ms;
}

.login-field input::placeholder { color: rgba(255, 255, 255, .42); }
.login-field input:hover { border-color: rgba(255, 255, 255, .32); }
.login-field input:-webkit-autofill,
.login-field input:-webkit-autofill:hover,
.login-field input:-webkit-autofill:focus {
  border-color: rgba(255, 255, 255, .24);
  -webkit-text-fill-color: #fff;
  caret-color: #fff;
  -webkit-box-shadow: 0 0 0 1000px #222 inset;
  transition: background-color 9999s ease-out 0s;
}

.login-field input:focus,
.login-field input:focus-visible {
  outline: none;
  border-color: rgba(255, 255, 255, .78);
  background: rgba(255, 255, 255, .11);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, .12);
}

.login-error {
  margin: -2px 0 0;
  padding: 10px 12px;
  border: 1px solid rgba(255, 140, 129, .42);
  border-radius: 10px;
  background: rgba(112, 25, 20, .42);
  color: #ffd4cf;
  font-size: 12px;
  line-height: 1.5;
}

.login-submit {
  min-height: 50px;
  margin-top: 2px;
  padding: 11px 18px;
  border: 1px solid #f2f0ea;
  border-radius: 10px;
  background: #f2f0ea;
  color: #0b0b0b;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .03em;
  box-shadow: 0 12px 34px rgba(0, 0, 0, .18);
  transition: background-color 150ms, border-color 150ms, transform 110ms, box-shadow 150ms;
}

.login-submit:hover:not(:disabled) {
  border-color: #fff;
  background: #fff;
  box-shadow: 0 16px 42px rgba(0, 0, 0, .24);
}

.login-submit:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
}

.session-note {
  margin: 26px 0 0;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, .11);
  color: rgba(255, 255, 255, .5);
  font-size: 11px;
  line-height: 1.65;
}

@keyframes film-reveal {
  from { opacity: 0; transform: scale(1.035); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes rise-in {
  from { opacity: 0; transform: translateY(22px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .login-shell {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(160px, 1fr) auto;
    gap: 28px;
    padding: 24px;
    overflow-y: auto;
  }

  .login-shell::before {
    background: linear-gradient(180deg, rgba(3, 3, 3, .4) 0%, rgba(3, 3, 3, .16) 26%, rgba(3, 3, 3, .9) 68%, #050505 100%);
  }

  .login-intro {
    grid-row: 2;
    align-self: end;
    padding: 52px 0 0;
  }

  .login-intro h1 { max-width: 680px; font-size: clamp(34px, 7.3vw, 54px); }
  .intro-copy { margin-top: 16px; }
  .login-panel { grid-row: 3; justify-self: end; width: min(100%, 480px); background: rgba(8, 8, 8, .88); }
}

@media (max-width: 560px) {
  .login-shell { gap: 22px; padding: 20px; }
  .login-brand { gap: 11px; }
  .login-brand span { letter-spacing: .14em; }
  .login-intro { padding-top: 36px; }
  .intro-label { margin-bottom: 12px; font-size: 9px; }
  .login-intro h1 { font-size: clamp(30px, 9.2vw, 42px); line-height: 1.16; }
  .intro-copy { font-size: 12px; }
  .login-panel { padding: 26px 22px; border-radius: 14px; }
  .panel-heading h2 { font-size: 26px; }
  .login-form { gap: 15px; margin-top: 24px; }
  .login-field input, .login-submit { min-height: 48px; }
  .session-note { margin-top: 22px; }
}

@media (prefers-reduced-motion: reduce) {
  .login-film,
  .login-brand,
  .login-intro,
  .login-panel { animation: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .login-panel {
    background: #111;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}
</style>
