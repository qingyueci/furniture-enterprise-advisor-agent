<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import DriftWall, { type DriftWallItem } from './DriftWall.vue'
import AccordionGallery from './AccordionGallery.vue'
import guide from '../data/styleGuide.json'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const popularityOpen = ref(false)
const popularityPinned = ref(false)
let closeTimer: number | null = null
const pairingOpen = ref(false)
const pairingPinned = ref(false)
const pairingVisible = computed(() => pairingOpen.value || pairingPinned.value)
const pairingButton = ref<HTMLButtonElement | null>(null)
let pairingCloseTimer: number | undefined
let pairingClickTimer: number | undefined
const pairingItems = guide.featured.map(id => {
 const group = guide.groups.find(group => group.items.some(item => item.id === id))!
 const item = group.items.find(item => item.id === id)!
 return { id, image: item.image, label: `${group.title} · ${item.title}` }
})
function closePairing() {
 window.clearTimeout(pairingCloseTimer); window.clearTimeout(pairingClickTimer)
 pairingOpen.value = false; pairingPinned.value = false
}
function previewPairing() {
 closePopularity(); window.clearTimeout(pairingCloseTimer); pairingOpen.value = true
}
function leavePairing(event?: FocusEvent) {
 if (event?.relatedTarget instanceof Element && event.relatedTarget.closest('#pairing-exhibition, #pairing-trigger')) return
 window.clearTimeout(pairingCloseTimer)
 if (!pairingPinned.value) pairingCloseTimer = window.setTimeout(() => {pairingOpen.value=false},160)
}
function clickPairing(event: MouseEvent) {
 window.clearTimeout(pairingClickTimer)
 if (event.detail > 1) return
 pairingClickTimer = window.setTimeout(() => {
  closePopularity(); pairingPinned.value = !pairingPinned.value; pairingOpen.value = pairingPinned.value
 },240)
}
function pairingDetail(id='') {
 closePairing(); closePopularity()
 void router.push({path:'/styles',hash:id ? `#${id}` : ''})
}
const roleLabel = computed(() => ({ ADMIN: '管理员', PRODUCT_MANAGER: '产品经理', SALES: '销售' }[auth.user?.role ?? 'SALES']))
const popularityItems: DriftWallItem[] = [
  { image: '/assets/furniture/popular/soft-01.webp', title: '云朵休闲椅', category: '软装' },
  { image: '/assets/furniture/popular/soft-02.webp', title: '胡桃木边几', category: '家具' },
  { image: '/assets/furniture/popular/soft-03.webp', title: '穹顶落地灯', category: '软装' },
  { image: '/assets/furniture/popular/soft-04.webp', title: '织物地毯组合', category: '软装' },
  { image: '/assets/furniture/popular/soft-05.webp', title: '弧面包覆椅', category: '家具' },
  { image: '/assets/furniture/popular/soft-06.webp', title: '异形装饰镜', category: '软装' },
  { image: '/assets/furniture/popular/soft-07.webp', title: '模块置物架', category: '家具' },
  { image: '/assets/furniture/popular/soft-08.webp', title: '浅木矮柜', category: '家具' },
  { image: '/assets/furniture/popular/soft-09.webp', title: '模块沙发', category: '软装' },
  { image: '/assets/furniture/popular/hardware-01.webp', title: '曲面柜门拉手', category: '五金' },
  { image: '/assets/furniture/popular/hardware-02.webp', title: '缓冲铰链', category: '五金' },
  { image: '/assets/furniture/popular/hardware-03.webp', title: '隐藏式滑轨', category: '五金' },
  { image: '/assets/furniture/popular/hardware-04.webp', title: '金属支撑脚', category: '五金' },
  { image: '/assets/furniture/popular/hardware-05.webp', title: '精密连接件', category: '五金' },
  { image: '/assets/furniture/popular/hardware-06.webp', title: '木作榫接节点', category: '家具' },
  { image: '/assets/furniture/popular/hardware-07.webp', title: '石材边几', category: '家具' },
  { image: '/assets/furniture/popular/hardware-08.webp', title: '烟熏玻璃灯具', category: '软装' },
  { image: '/assets/furniture/popular/hardware-09.webp', title: '异形收纳件', category: '家具' },
]
const exhibitionVisible = computed(() => popularityOpen.value || popularityPinned.value)
const navigation = computed(() => [
  { to: '/agent', label: 'Agent 产品分析', code: 'AG', show: true },
  { to: '/products', label: '产品与价格', code: 'PR', show: true },
  { to: '/documents', label: '产品资料管理', code: 'DC', show: auth.isAdmin },
  { to: '/users', label: '用户管理', code: 'US', show: auth.isAdmin },
  { to: '/audit-logs', label: '审计日志', code: 'AU', show: auth.isAdmin },
].filter(item => item.show))

async function signOut() {
  await auth.logout()
  await router.replace('/login')
}

function clearCloseTimer() {
  if (closeTimer) window.clearTimeout(closeTimer)
  closeTimer = null
}

function openPopularityPreview() {
  closePairing()
  clearCloseTimer()
  popularityOpen.value = true
}

function schedulePopularityClose() {
  clearCloseTimer()
  if (popularityPinned.value) return
  closeTimer = window.setTimeout(() => { popularityOpen.value = false }, 160)
}

function togglePopularity() {
  closePairing()
  clearCloseTimer()
  popularityPinned.value = !popularityPinned.value
  popularityOpen.value = popularityPinned.value
}

function closePopularity() {
  clearCloseTimer()
  popularityPinned.value = false
  popularityOpen.value = false
}

function handleOutsidePointer(event: PointerEvent) {
  if (!exhibitionVisible.value && !pairingVisible.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('[aria-controls=popular-exhibition], #popular-exhibition, #pairing-trigger, #pairing-exhibition')) return
  closePopularity(); closePairing()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { const wasOpen=pairingVisible.value; closePopularity(); closePairing(); if(wasOpen) pairingButton.value?.focus() }
}

watch(() => route.fullPath, () => { closePopularity(); closePairing() })
onMounted(() => {
  document.addEventListener('pointerdown', handleOutsidePointer)
  document.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => {
  closePairing()
  clearCloseTimer()
  document.removeEventListener('pointerdown', handleOutsidePointer)
  document.removeEventListener('keydown', handleKeydown)
})

</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <div class="topbar">
        <RouterLink class="brand" to="/agent"><span class="brand-mark">PA</span><span><b>企业产品分析</b><small>Evidence Workbench</small></span></RouterLink>
        <strong class="project-title" title="《多维度安全管控的家具企业顾问Agent系统设计》">《多维度安全管控的家具企业顾问Agent系统设计》</strong>
        <div class="quick-actions" aria-label="展览页入口">
          <button class="top-action" type="button" :aria-expanded="exhibitionVisible" aria-controls="popular-exhibition" title="打开人气单品展览" @mouseenter="openPopularityPreview" @mouseleave="schedulePopularityClose" @focus="openPopularityPreview" @blur="schedulePopularityClose" @click="togglePopularity">人气单品</button>
          <button id="pairing-trigger" ref="pairingButton" class="top-action" type="button" :aria-expanded="pairingVisible" aria-controls="pairing-exhibition" title="悬停预览，单击固定，双击查看全部风格" @mouseenter="previewPairing" @mouseleave="leavePairing()" @click="clickPairing" @dblclick="pairingDetail()" @keydown.enter.prevent="pairingDetail()">热门搭配</button>
        </div>
        <div class="user-zone"><span><b>{{ auth.user?.username }}</b><small>{{ roleLabel }} · {{ auth.user?.role }}</small></span><button class="button" @click="signOut">退出</button></div>
      </div>
      <nav class="top-navigation" aria-label="主导航">
        <div class="nav-links">
          <RouterLink v-for="item in navigation" :key="item.to" class="nav-link" :to="item.to" :class="{ active: route.path === item.to }" :aria-current="route.path === item.to ? 'page' : undefined">
            <span class="nav-link-content"><span class="nav-code" aria-hidden="true">{{ item.code }}</span><span>{{ item.label }}</span></span>
          </RouterLink>
        </div>
      </nav>
      <section id="popular-exhibition" class="exhibition-popover" :class="{ 'is-open': exhibitionVisible }" aria-label="人气单品展览" :aria-hidden="!exhibitionVisible" @mouseenter="openPopularityPreview" @mouseleave="schedulePopularityClose" @click.stop>
        <div class="exhibition-popover-head"><div><span>POPULAR PRODUCTS</span><strong>人气单品</strong><small>软装、家具与五金的灵感选集</small></div><button class="exhibition-close" type="button" aria-label="关闭人气单品展览" @click="closePopularity">收起</button></div>
        <div class="exhibition-wall"><DriftWall :items="popularityItems" :columns="5" :tile-width="176" :tile-height="116" :gap="14" :tilt="13" :turn="-11" :perspective="1200" :depth="90" :speed="24" direction="up" :variance="0.35" :parallax="0.35" :lift="38" :fade="0.6" :dim="0.55" overlay-color="#161412" /></div>
      </section>
      <section id="pairing-exhibition" class="exhibition-popover pairing-popover" :class="{'is-open':pairingVisible}" :inert="!pairingVisible" :aria-hidden="!pairingVisible" aria-label="热门搭配展览" @mouseenter="previewPairing" @mouseleave="leavePairing()" @focusin="previewPairing" @focusout="leavePairing($event)">
        <div class="exhibition-popover-head"><div><span>STYLE ATLAS</span><strong>热门搭配</strong><small>四类风格 · 八个灵感切面 · 双击图片查看介绍</small></div><div class="pairing-actions"><button class="exhibition-close" @click="pairingDetail()">查看全部风格</button><button class="exhibition-close" @click="closePairing">收起</button></div></div>
        <div class="exhibition-wall"><AccordionGallery v-if="pairingVisible" :items="pairingItems" :default-index="null" :expand-ratio=".52" trigger="hover" @detail="pairingDetail" /></div>
      </section>
    </header>
    <main class="main-workspace"><RouterView /></main>
  </div>
</template>

<style scoped>
.app-shell { --topbar-height: 116px; --workspace-scale: 1; min-height: 100vh; }
.site-header { position: sticky; top: 0; z-index: 20; background: rgba(255,254,251,.94); border-bottom: 1px solid var(--color-border); backdrop-filter: blur(18px); }
.topbar { height: 64px; display: flex; align-items: center; gap: 28px; padding: 0 28px; }
.brand { display: flex; align-items: center; gap: 11px; color: var(--color-text-primary); text-decoration: none; flex-shrink: 0; }
.brand-mark { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; background: var(--color-accent); color: var(--color-surface); font-size: 12px; font-weight: 800; box-shadow: 0 7px 18px rgba(25,24,22,.18); }
.brand b, .brand small { display: block; }
.brand b { font-size: 14px; }
.brand small { margin-top: 3px; color: var(--color-text-tertiary); font-size: 10px; }
.project-title { flex: 1; min-width: 80px; overflow: hidden; color: var(--color-text-secondary); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.quick-actions { display: flex; gap: 8px; margin-left: auto; }
.top-action { min-height: 36px; padding: 7px 14px; border: 1px solid var(--color-border); border-radius: 999px; background: var(--color-surface); color: var(--color-accent); cursor: pointer; font-size: 12px; font-weight: 600; transition: background-color 180ms, border-color 180ms, box-shadow 180ms; }
.top-action:hover, .top-action[aria-expanded='true'] { border-color: var(--color-accent); background: var(--color-accent-soft); box-shadow: 0 7px 18px rgba(25,24,22,.1); }
.top-action:disabled { cursor: not-allowed; opacity: .7; }
.user-zone { display: flex; align-items: center; gap: 14px; margin-left: auto; }
.user-zone > span { display: grid; text-align: right; }
.user-zone b { font-size: 13px; }
.user-zone small { margin-top: 2px; color: var(--color-text-tertiary); font-size: 11px; }
.top-navigation { position: relative; display: flex; align-items: stretch; gap: 12px; height: 51px; padding: 0 28px; }
.nav-links { position: relative; display: flex; align-items: stretch; gap: 12px; width: max-content; height: 100%; }
.top-navigation a { position: relative; z-index: 1; display: flex; align-items: center; gap: 9px; padding: 0 18px; overflow: hidden; border-bottom: 3px solid transparent; border-radius: 10px 10px 0 0; color: var(--color-text-secondary); text-decoration: none; font-size: 14px; font-weight: 600; }
.nav-link-content { position: relative; z-index: 1; display: flex; align-items: center; gap: 9px; }
.top-navigation a:hover { background: rgba(247,244,237,.42); color: var(--color-accent); }
.top-navigation a.active { border-bottom-color: var(--color-accent); background: linear-gradient(180deg, transparent, var(--color-accent-soft)); color: var(--color-accent); }
.nav-code { display: grid; place-items: center; width: 20px; height: 20px; border: 0; border-radius: 4px; background: transparent; color: var(--color-text-muted); font-size: 8px; font-weight: 500; }
.top-navigation a.active .nav-code { border-color: var(--color-accent); }
.main-workspace { min-width: 0; padding: 28px; }
.exhibition-popover { position: absolute; top: 64px; right: 0; left: 0; z-index: 30; display: flex; flex-direction: column; height: 66.666vh; min-height: 300px; padding: 16px 28px 18px; overflow: hidden; border-top: 1px solid rgba(255,255,255,.15); background: rgba(27,25,22,.94); box-shadow: 0 24px 50px rgba(31,28,24,.2); backdrop-filter: blur(18px) saturate(1.1); opacity: 0; pointer-events: none; transform: translateY(-14px) scale(.985); visibility: hidden; transition: opacity 240ms ease, transform 240ms ease, visibility 240ms; }
.exhibition-popover.is-open { opacity: 1; pointer-events: auto; transform: translateY(0); visibility: visible; }
.exhibition-popover-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-shrink: 0; color: #f5f0e7; }
.exhibition-popover-head div { display: grid; gap: 3px; }
.exhibition-popover-head span { color: #b5aa9a; font-size: 9px; font-weight: 700; letter-spacing: .18em; }
.exhibition-popover-head strong { font-size: 18px; letter-spacing: .05em; }
.exhibition-popover-head small { color: #b5aa9a; font-size: 11px; }
.exhibition-close { padding: 7px 11px; border: 1px solid rgba(255,255,255,.24); border-radius: 999px; background: transparent; color: #eee8df; cursor: pointer; font-size: 11px; }
.exhibition-close:hover, .exhibition-close:focus-visible { border-color: #eee8df; background: rgba(255,255,255,.1); }
.exhibition-wall { flex: 1; min-height: 0; margin-top: 8px; }
.exhibition-wall :deep(.drift-wall) { border-top: 1px solid rgba(255,255,255,.1); }
@media (max-width: 1180px) {
  .topbar { gap: 14px; padding: 0 20px; overflow-x: auto; }
  .brand small, .user-zone small { display: none; }
  .top-navigation { gap: 4px; padding: 0 20px; overflow-x: auto; }
  .nav-links { gap: 4px; }
  .top-navigation a { flex: 0 0 auto; padding: 0 12px; }
  .main-workspace { padding: 20px; }
  .exhibition-popover { height: 66.666vh; padding-inline: 20px; }
  .exhibition-wall :deep(.drift-wall) { --dw-tile-w: 150px; --dw-tile-h: 100px; }
}
@media (max-width: 760px) {
  .project-title { max-width: 180px; flex: 0 0 180px; }
  .user-zone > span { display: none; }
  .main-workspace { padding: 12px; }
  .exhibition-popover { height: 66.666vh; min-height: 240px; padding: 13px 12px 14px; }
  .exhibition-popover-head strong { font-size: 16px; }
  .exhibition-popover-head small { font-size: 10px; }
  .exhibition-wall :deep(.drift-wall) { --dw-tile-w: 118px; --dw-tile-h: 82px; }
}
.pairing-popover{height:66.666dvh;min-height:0;border-radius:0 0 18px 18px;box-sizing:border-box}
.pairing-actions{display:flex!important;flex-direction:row;gap:8px!important}
@media(prefers-reduced-motion:reduce){.pairing-popover{transition:none}}

/* C｜文档情报：深紫画布承托暖白纸张面板，红色只承担焦点与待核验提示。 */
.app-shell {
  --color-canvas: #2a1f35;
  --color-surface: #f2ece2;
  --color-surface-subtle: #eee5db;
  --color-surface-inset: #e8ded3;
  --color-text-primary: #251d30;
  --color-text-secondary: #5b4c5d;
  --color-text-tertiary: #6b6070;
  --color-text-muted: #aa9eaa;
  --color-border: #d6c9be;
  --color-border-soft: #e7ddd3;
  --color-accent: #7d303b;
  --color-accent-hover: #65232f;
  --color-accent-soft: #efd9d7;
  --color-focus: #7d303b;
  --color-success: #203429;
  --color-success-soft: #dce8df;
  --color-warning: #9a6412;
  --color-warning-soft: #f6e9c9;
  --color-danger: #7d303b;
  --color-danger-soft: #efd9d7;
  --font-serif: "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", serif;
  --font-sans: "Inter", "Segoe UI", "Microsoft YaHei", sans-serif;
  --shadow-popover: 0 24px 60px rgba(11, 10, 10, .35);
  color: var(--color-surface);
  background: var(--color-canvas);
}
.site-header {
  color: var(--color-surface);
  background: rgba(42, 31, 53, .96);
  border-bottom-color: rgba(242, 236, 226, .2);
  box-shadow: 0 10px 30px rgba(11, 10, 10, .22);
}
.brand { color: var(--color-surface); }
.brand-mark {
  border: 1px solid rgba(242, 236, 226, .38);
  background: rgba(11, 10, 10, .4);
  color: var(--color-surface);
  box-shadow: 0 8px 22px rgba(11, 10, 10, .3);
}
.brand b { font-family: var(--font-serif); letter-spacing: .04em; }
.brand small, .user-zone small { color: rgba(242, 236, 226, .68); }
.project-title { color: rgba(242, 236, 226, .9); font-family: var(--font-serif); }
.top-action {
  border-color: rgba(242, 236, 226, .34);
  background: transparent;
  color: var(--color-surface);
}
.top-action:hover, .top-action[aria-expanded='true'] {
  border-color: var(--color-surface);
  background: rgba(125, 48, 59, .42);
  box-shadow: 0 8px 20px rgba(11, 10, 10, .28);
}
.user-zone .button {
  border-color: rgba(242, 236, 226, .34);
  background: transparent;
  color: var(--color-surface);
}
.user-zone .button:hover { border-color: var(--color-surface); background: rgba(125, 48, 59, .42); }
.top-navigation {
  border-top: 1px solid rgba(242, 236, 226, .1);
  background: rgba(11, 10, 10, .15);
}
.top-navigation a { color: rgba(242, 236, 226, .74); }
.top-navigation a::after {
  position: absolute;
  right: 14px;
  bottom: 0;
  left: 14px;
  height: 2px;
  content: '';
  background: var(--color-surface);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 220ms cubic-bezier(.22, 1, .36, 1);
}
.top-navigation a:hover { background: rgba(242, 236, 226, .08); color: var(--color-surface); }
.top-navigation a.active {
  border-bottom-color: transparent;
  background: rgba(242, 236, 226, .14);
  color: var(--color-surface);
}
.top-navigation a.active::after { transform: scaleX(1); }
.nav-code { color: rgba(242, 236, 226, .54); }
.top-navigation a.active .nav-code { color: var(--color-surface); }
.main-workspace {
  background: var(--color-canvas);
  color: var(--color-text-primary);
}
.exhibition-popover {
  background: rgba(42, 31, 53, .97);
  border-top-color: rgba(242, 236, 226, .2);
  box-shadow: 0 24px 60px rgba(11, 10, 10, .42);
}
.exhibition-popover.is-open { transform: translateY(0) scale(1); }
.exhibition-close { border-color: rgba(242, 236, 226, .3); }
.exhibition-close:hover, .exhibition-close:focus-visible { border-color: var(--color-surface); background: rgba(125, 48, 59, .35); }
@media (prefers-reduced-motion: reduce) {
  .top-navigation a::after { transition: none; }
}
</style>
