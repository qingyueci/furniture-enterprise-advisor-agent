<script setup lang="ts">
// Vue port of React Bits AccordionGallery (JS-CSS): GSAP flex, tilt and media parallax.
import { gsap } from 'gsap'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = withDefaults(defineProps<{ items: { image: string; label: string; id: string }[]; defaultIndex?: number | null; expandRatio?: number; trigger?: 'hover' | 'click' }>(), { defaultIndex: null, expandRatio: .52, trigger: 'hover' })
const emit = defineEmits<{ detail: [id: string] }>()
const root = ref<HTMLElement | null>(null)
const active = ref<number | null>(typeof props.defaultIndex === 'number' ? props.defaultIndex : null)
let observer: ResizeObserver | undefined
let timeline: gsap.core.Timeline | undefined
let motion: MediaQueryList | undefined
function layout() {
 if (!root.value) return
 const panels = Array.from(root.value.querySelectorAll<HTMLElement>('.ag-panel'))
 const narrow = root.value.clientWidth < 520
 const ratio = Math.min(.9, Math.max(.2, props.expandRatio))
 const activeIndex = active.value
 timeline?.kill(); timeline = gsap.timeline()
 panels.forEach((panel, i) => {
  const selected = i === activeIndex
  const duration = motion?.matches ? 0 : .6
  timeline!.to(panel, {flexGrow: narrow ? 0 : selected ? ratio*(panels.length-1)/(1-ratio) : 1, rotateY: narrow ? 0 : selected ? 0 : activeIndex !== null && i < activeIndex ? 8 : -8, duration, ease: 'power3.out'},0)
 })
}
function select(index:number) { active.value=index }
function keyboard(event:KeyboardEvent,index:number) {
 if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'].includes(event.key)) { event.preventDefault(); const next=(index+(['ArrowRight','ArrowDown'].includes(event.key)?1:-1)+props.items.length)%props.items.length; select(next); root.value?.querySelectorAll<HTMLButtonElement>('.ag-panel')[next]?.focus() }
 if(event.key==='Enter') {event.preventDefault(); emit('detail',props.items[index]!.id)}
}
watch(active,layout)
onMounted(async()=>{motion=matchMedia('(prefers-reduced-motion: reduce)');motion.addEventListener('change',layout); await nextTick();observer=new ResizeObserver(layout);if(root.value)observer.observe(root.value);layout()})
onBeforeUnmount(()=>{timeline?.kill();observer?.disconnect();motion?.removeEventListener('change',layout)})
</script>
<template>
 <div ref="root" class="accordion-gallery" aria-label="四类风格精选">
  <button v-for="(item,i) in items" :key="item.id" type="button" class="ag-panel" :class="{selected:i===active}" :aria-label="item.label+'，双击或回车查看介绍'" @mouseenter="trigger==='hover' && select(i)" @focus="select(i)" @click="select(i)" @dblclick="emit('detail',item.id)" @keydown="keyboard($event,i)">
   <span class="ag-frame"><span class="ag-backdrop" aria-hidden="true"><img :src="item.image" alt="" draggable="false" /></span><span class="ag-media"><img :src="item.image" :alt="item.label" draggable="false" /></span><span class="ag-overlay" /></span><span class="ag-label">{{item.label}}</span>
  </button>
 </div>
</template>
<style scoped>
.accordion-gallery{display:flex;width:100%;height:100%;gap:10px;perspective:1400px;overflow:hidden;padding:4px;box-sizing:border-box}
.ag-panel{position:relative;flex:1 1 0;min-width:0;min-height:0;border:0;padding:0;overflow:hidden;border-radius:12px;background:#191817;cursor:pointer;transform-style:preserve-3d;color:#fff;outline-offset:-3px}
.ag-panel:focus-visible{outline:2px solid #fff}
.ag-frame{position:absolute;inset:0;overflow:hidden;background:#191817}.ag-backdrop{position:absolute;inset:-22px;z-index:0;overflow:hidden;opacity:0;pointer-events:none;transform:scale(1.06);filter:blur(18px) brightness(.52);transition:opacity .35s ease,transform .6s ease}.ag-backdrop img{width:100%;height:100%;object-fit:cover;display:block}.selected .ag-backdrop{opacity:.58;transform:scale(1.1)}.ag-media{position:absolute;inset:0;z-index:1}.ag-media img{width:100%;height:100%;object-fit:cover;object-position:center;display:block}.selected .ag-media img{object-fit:contain}
.ag-overlay{position:absolute;inset:0;background:transparent;opacity:0}.ag-label{position:absolute;bottom:20px;left:18px;right:10px;text-align:left;font-size:15px;font-weight:600;text-shadow:0 2px 8px #000;opacity:0;transition:opacity .3s}.selected .ag-label{opacity:1}
@media(max-width:519px){.accordion-gallery{overflow-x:auto;scroll-snap-type:x proximity;perspective:none}.ag-panel{flex:0 0 78%!important;scroll-snap-align:start}.ag-label{opacity:1}}
@media(prefers-reduced-motion:reduce){.ag-backdrop,.ag-label{transition:none}}
</style>
