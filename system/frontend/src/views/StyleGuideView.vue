<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import guide from '../data/styleGuide.json'
const route=useRoute()
async function locate(){await nextTick();if(route.hash) document.getElementById(route.hash.slice(1))?.scrollIntoView({block:'start'}); else window.scrollTo({top:0})}
onMounted(locate);watch(()=>route.hash,locate)
</script>
<template>
 <article class="style-guide">
  <header class="guide-intro"><span>STYLE ATLAS · 热门搭配</span><h1>空间的气质，从风格开始。</h1><p>{{guide.notice}}</p><small>图文来源：风格示例 · AI视觉例图，非实际项目案例</small></header>
  <nav class="guide-nav" aria-label="风格分类"><a v-for="group in guide.groups" :key="group.id" :href="'#'+group.id">{{group.title}}</a><a href="#principles">搭配原则</a></nav>
  <section class="quick"><h2>快速选择</h2><dl><div v-for="item in guide.quick" :key="item.goal"><dt>{{item.goal}}</dt><dd>{{item.styles}}</dd></div></dl></section>
  <section v-for="group in guide.groups" :id="group.id" :key="group.id" class="style-section"><header><h2>{{group.title}}</h2><span>{{group.items.length}} 种风格</span></header><div class="style-grid"><article v-for="item in group.items" :id="item.id" :key="item.id" class="style-card"><img :src="item.image" :alt="item.title" loading="lazy" decoding="async"/><div><h3>{{item.title}}</h3><p>{{item.description}}</p></div></article></div></section>
  <section id="principles" class="principles"><h2>搭配时的控制原则</h2><ol><li v-for="item in guide.principles" :key="item.title"><strong>{{item.title}}</strong><p>{{item.description}}</p></li></ol></section>
 </article>
</template>
<style scoped>
.style-guide { max-width: 1440px; margin: auto; color: var(--color-surface); }
.guide-intro { max-width: 850px; padding: 38px 0 28px; }
.guide-intro span { color: rgba(242,236,226,.78); font-size: 11px; letter-spacing: .16em; }
.guide-intro h1 { margin: 14px 0; color: var(--color-surface); font-family: var(--font-serif); font-size: clamp(26px,3vw,46px); letter-spacing: -.025em; }
.guide-intro p { color: rgba(242,236,226,.74); font-size: 15px; line-height: 1.9; }
.guide-intro small { color: rgba(242,236,226,.56); }
.guide-nav { display: flex; flex-wrap: wrap; gap: 10px; padding: 16px 0; border-block: 1px solid rgba(242,236,226,.24); }
.guide-nav a { padding: 10px 16px; border: 1px solid rgba(242,236,226,.34); border-radius: 24px; color: rgba(242,236,226,.84); text-decoration: none; transition: background-color 180ms, border-color 180ms, transform 180ms; }
.guide-nav a:hover, .guide-nav a:focus-visible { border-color: var(--color-surface); background: rgba(125,48,59,.4); color: var(--color-surface); transform: translateY(-2px); }
.quick { margin: 30px 0; }
.quick h2, .style-section > header h2, .principles h2 { color: var(--color-surface); font-family: var(--font-serif); }
.quick dl { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; }
.quick dl > div { padding: 16px; border-left: 2px solid var(--color-accent); background: #f0e8df; color: var(--color-text-primary); }
.quick dt { font-weight: 600; }
.quick dd { margin: 8px 0 0; color: var(--color-text-secondary); line-height: 1.7; }
.style-section, .principles { margin: 44px 0; scroll-margin-top: 135px; }
.style-section > header { display: flex; align-items: center; justify-content: space-between; }
.style-section > header span { color: rgba(242,236,226,.62); font-size: 12px; }
.style-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 24px; }
.style-card { overflow: hidden; border: 1px solid #e0d9cf; border-radius: 12px; background: #fffdf9; color: var(--color-text-primary); scroll-margin-top: 135px; }
.style-card:target { outline: 2px solid var(--color-accent); }
.style-card img { display: block; width: 100%; height: 240px; object-fit: cover; }
.style-card > div { padding: 20px; }
.style-card h3 { margin: 0 0 10px; font-size: 18px; }
.style-card p, .principles p { margin: 0; color: var(--color-text-secondary); font-size: 14px; line-height: 1.9; }
.principles li { padding: 10px; color: rgba(242,236,226,.82); }
.principles strong { display: block; margin-bottom: 5px; color: var(--color-surface); }
.principles p { color: rgba(242,236,226,.74); }
@media(max-width:1050px){.style-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.style-grid,.quick dl{grid-template-columns:1fr}.guide-intro{padding-top:15px}}
@media(prefers-reduced-motion:reduce){.guide-nav a{transition:none}}
</style>
