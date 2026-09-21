<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type SpiralItem = { src: string; alt: string }
const props = withDefaults(defineProps<{
  items: SpiralItem[]; speed?: number; animationMode?: 'auto' | 'scroll' | 'drag' | 'all'; radius?: number;
  cardWidth?: number; cardHeight?: number; verticalSpacing?: number; perspective?: number; cardRadius?: number;
  centerScale?: number; edgeBlur?: number; cardsPerTurn?: number; pauseOnHover?: boolean
}>(), { speed: .55, animationMode: 'all', radius: 170, cardWidth: 100, cardHeight: 100, verticalSpacing: 60, perspective: 1000, cardRadius: 10, centerScale: 1.2, edgeBlur: 6, cardsPerTurn: 7, pauseOnHover: true })

const root = ref<HTMLElement | null>(null)
const cards = ref<HTMLElement[]>([])
const styleVars = computed(() => ({ perspective: `${props.perspective}px`, '--spiral-card-width': `${props.cardWidth}px`, '--spiral-card-height': `${props.cardHeight}px`, '--spiral-card-radius': `${props.cardRadius}px` }))
let frame = 0, progress = 0, target = 0, autoSpeed = 0, previous = 0, lastScrollY = 0, lastPointerY = 0
let bounds = { width: 1, height: 1 }, visible = true, hovered = false, dragging = false, dragMoved = false
let resizeObserver: ResizeObserver | null = null, intersectionObserver: IntersectionObserver | null = null
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max)
const modulo = (v: number, divisor: number) => ((v % divisor) + divisor) % divisor
const smoothstep = (min: number, max: number, value: number) => { const x = clamp((value - min) / (max - min || 1), 0, 1); return x * x * (3 - 2 * x) }

function render(time: number) {
  const delta = Math.min((time - (previous || time)) / 1000, .05); previous = time
  const autoEnabled = props.animationMode === 'auto' || props.animationMode === 'all'
  const active = visible && !document.hidden && !reduced.matches && !(dragging || (props.pauseOnHover && hovered))
  const blend = 1 - Math.exp(-delta * 7)
  autoSpeed += ((autoEnabled && active ? props.speed : 0) - autoSpeed) * blend
  target += autoSpeed * delta
  progress += (target - progress) * (1 - Math.exp(-delta * (dragging ? 22 : 11)))
  const count = props.items.length, half = count / 2
  const fit = Math.min(1, bounds.width / (props.cardWidth * 2.8), bounds.height / (props.cardHeight * 2.35))
  const responsiveRadius = Math.min(props.radius, Math.max(72, bounds.width * .36)) * fit
  cards.value.forEach((card, index) => {
    let offset = modulo(index - progress + half, count) - half
    const edge = Math.min(Math.abs(offset) / Math.max(half, 1), 1)
    const opacity = 1 - smoothstep(.3, 1, edge)
    const focus = 1 - Math.min(Math.abs(offset) / Math.max(props.cardsPerTurn * .65, 1), 1)
    const angle = offset * (360 / Math.max(props.cardsPerTurn, 1)) * Math.PI / 180
    const x = Math.sin(angle) * responsiveRadius, z = Math.cos(angle) * responsiveRadius
    const depthScale = clamp(props.perspective / Math.max(props.perspective - z, 1), .72, 1.45)
    const scale = (1 + (props.centerScale - 1) * focus) * fit * depthScale
    card.style.transform = `translate(-50%, -50%) translate3d(${x}px, ${offset * props.verticalSpacing * fit}px, 0) scale(${scale})`
    card.style.opacity = opacity.toFixed(3); card.style.filter = `${props.edgeBlur * smoothstep(.35, 1, edge) > .01 ? `blur(${(props.edgeBlur * smoothstep(.35, 1, edge)).toFixed(2)}px)` : 'none'}`
    card.style.zIndex = String(Math.round(((z / Math.max(responsiveRadius, 1) + 1) / 2) * 100000) + index)
  })
  frame = requestAnimationFrame(render)
}
function onScroll() { const next = window.scrollY, delta = next - lastScrollY; lastScrollY = next; if ((props.animationMode === 'scroll' || props.animationMode === 'all') && visible) target += clamp((delta * props.speed / .55) / Math.max(props.verticalSpacing * 2, 1), -1.5, 1.5) }
function pointerDown(event: PointerEvent) { if (!['drag', 'all'].includes(props.animationMode) || event.button !== 0) return; dragging = true; dragMoved = false; lastPointerY = event.clientY; target = progress; root.value?.setPointerCapture(event.pointerId) }
function pointerMove(event: PointerEvent) { if (!dragging) return; const delta = event.clientY - lastPointerY; lastPointerY = event.clientY; if (Math.abs(delta) > .5) dragMoved = true; target -= delta / Math.max(props.verticalSpacing, 1) }
function pointerUp(event: PointerEvent) { dragging = false; if (root.value?.hasPointerCapture(event.pointerId)) root.value.releasePointerCapture(event.pointerId) }
function enter() { hovered = true }
function leave() { hovered = false }
function captureClick(event: MouseEvent) { if (dragMoved) { event.preventDefault(); event.stopPropagation(); dragMoved = false } }
function stop() { cancelAnimationFrame(frame); resizeObserver?.disconnect(); intersectionObserver?.disconnect(); window.removeEventListener('scroll', onScroll) }
onMounted(() => { if (!root.value || !props.items.length) return; bounds = root.value.getBoundingClientRect(); lastScrollY = window.scrollY; resizeObserver = new ResizeObserver(() => { if (root.value) bounds = root.value.getBoundingClientRect() }); resizeObserver.observe(root.value); intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting }, { threshold: .02 }); intersectionObserver.observe(root.value); window.addEventListener('scroll', onScroll, { passive: true }); frame = requestAnimationFrame(render) })
onBeforeUnmount(stop)
watch(() => props.items, () => { cards.value = cards.value.slice(0, props.items.length) })
</script>

<template>
  <div ref="root" class="infinite-spiral" :style="styleVars" aria-label="艺术家具产品螺旋" @mouseenter="enter" @mouseleave="leave" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointerUp" @click.capture="captureClick">
    <div class="infinite-spiral__stage" role="list">
      <div v-for="(item, index) in items" :key="item.src" :ref="el => { if (el) cards[index] = el as HTMLElement }" class="infinite-spiral__item" role="listitem">
        <img :src="item.src" :alt="item.alt" :loading="index < 6 ? 'eager' : 'lazy'" draggable="false" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.infinite-spiral { position: relative; width: 100%; height: 100%; min-height: 320px; overflow: hidden; isolation: isolate; cursor: grab; touch-action: pan-x; user-select: none; }
.infinite-spiral:active { cursor: grabbing; }
.infinite-spiral__stage { position: absolute; inset: 0; transform-style: preserve-3d; }
.infinite-spiral__item { position: absolute; top: 50%; left: 50%; width: var(--spiral-card-width); height: var(--spiral-card-height); overflow: hidden; border: 1px solid rgba(255,255,255,.62); border-radius: var(--spiral-card-radius); background: rgba(255,255,255,.34); box-shadow: 0 14px 38px rgba(30,24,18,.18); backface-visibility: hidden; will-change: transform, opacity, filter; }
.infinite-spiral__item img { display: block; width: 100%; height: 100%; object-fit: cover; user-select: none; }
@media (prefers-reduced-motion: reduce) { .infinite-spiral__item { will-change: auto; } }
</style>
