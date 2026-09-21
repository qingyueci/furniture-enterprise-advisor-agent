<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export type DriftWallItem = {
  image: string
  title: string
  category: '软装' | '家具' | '五金'
  href?: string
}

const props = withDefaults(defineProps<{
  items: DriftWallItem[]
  columns?: number
  tileWidth?: number
  tileHeight?: number
  gap?: number
  radius?: number
  tilt?: number
  turn?: number
  roll?: number
  perspective?: number
  depth?: number
  speed?: number
  direction?: 'up' | 'down'
  variance?: number
  parallax?: number
  pauseOnHover?: boolean
  lift?: number
  fade?: number
  dim?: number
  grayscale?: boolean
  overlayColor?: string
}>(), {
  columns: 5,
  tileWidth: 176,
  tileHeight: 116,
  gap: 14,
  radius: 12,
  tilt: 13,
  turn: -11,
  roll: 0,
  perspective: 1200,
  depth: 90,
  speed: 24,
  direction: 'up',
  variance: 0.35,
  parallax: 0.35,
  pauseOnHover: true,
  lift: 38,
  fade: 0.6,
  dim: 0.55,
  grayscale: false,
  overlayColor: '#161412',
})

const root = ref<HTMLElement | null>(null)
const plane = ref<HTMLElement | null>(null)
const tracks = ref<HTMLElement[]>([])
const containerHeight = ref(600)
const activeId = ref<string | null>(null)
const reduced = ref(false)
const responsiveColumns = ref(props.columns)
const items = computed(() => props.items.filter(item => item.image))
const columnItems = computed(() => {
  const columns = Array.from({ length: Math.max(1, responsiveColumns.value) }, () => [] as DriftWallItem[])
  items.value.forEach((item, index) => columns[index % columns.length].push(item))
  return columns.map(column => column.length ? column : items.value.slice(0, 1))
})
const columnMeta = computed(() => {
  const unit = props.tileHeight + props.gap
  return columnItems.value.map(column => {
    const copyHeight = Math.max(unit, column.length * unit)
    const copies = Math.max(2, Math.ceil((containerHeight.value * 1.6) / copyHeight) + 1)
    return { copyHeight, copies }
  })
})
const cssVars = computed(() => ({
  '--dw-tile-w': `${props.tileWidth}px`,
  '--dw-tile-h': `${props.tileHeight}px`,
  '--dw-gap': `${props.gap}px`,
  '--dw-radius': `${props.radius}px`,
  '--dw-perspective': `${props.perspective}px`,
  '--dw-lift': `${props.lift}px`,
  '--dw-dim': props.dim,
  '--dw-gray': props.grayscale ? 1 : 0,
  '--dw-overlay': props.overlayColor,
  '--dw-edge': `${Math.max(0, (1 - props.fade) * 100)}%`,
}))

const offsets: number[] = []
const velocities: number[] = []
let frame = 0
let previous = 0
let hoveredColumn = -1
let wallHovered = false
let visible = true
let pointer = { x: 0, y: 0 }
let pointerDamped = { x: 0, y: 0 }
let resizeObserver: ResizeObserver | null = null
let intersectionObserver: IntersectionObserver | null = null
let motionQuery: MediaQueryList | null = null

const columnFactor = (index: number) => 1 + props.variance * ((((index * 0.6180339887 + 0.35) % 1) * 2) - 1)
const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

function applyPlaneTransform(px: number, py: number) {
  if (!plane.value) return
  plane.value.style.transform = `translate(-50%, -50%) scale(1.18) rotateX(${props.tilt + py}deg) rotateY(${props.turn + px}deg) rotateZ(${props.roll}deg) translateZ(${-props.depth}px)`
}

function render(time: number) {
  const delta = Math.min((time - (previous || time)) / 1000, 0.05)
  previous = time
  const autoEnabled = !reduced.value && visible && !document.hidden
  const paused = wallHovered && props.pauseOnHover
  const direction = props.direction === 'up' ? 1 : -1
  const damp = 1 - Math.exp(-delta / 0.12)
  const targetX = pointer.x * props.parallax * 8
  const targetY = -pointer.y * props.parallax * 8
  pointerDamped.x += (targetX - pointerDamped.x) * damp
  pointerDamped.y += (targetY - pointerDamped.y) * damp
  applyPlaneTransform(pointerDamped.x, pointerDamped.y)

  const bounds = root.value?.getBoundingClientRect()
  const fit = bounds ? Math.min(1, bounds.width / (props.tileWidth * 4.4), bounds.height / (props.tileHeight * 2.7)) : 1
  const radius = Math.min(props.tileWidth, Math.max(90, (bounds?.width ?? 900) * 0.26)) * fit
  columnItems.value.forEach((_, columnIndex) => {
    const meta = columnMeta.value[columnIndex]
    const track = tracks.value[columnIndex]
    if (!meta || !track) return
    const baseVelocity = props.speed * columnFactor(columnIndex) * direction * (columnIndex % 2 === 0 ? 1 : -1)
    const targetVelocity = autoEnabled && !paused && hoveredColumn !== columnIndex ? baseVelocity : 0
    const ease = 1 - Math.exp(-delta / (targetVelocity === 0 ? 0.16 : 0.28))
    velocities[columnIndex] = (velocities[columnIndex] ?? 0) + (targetVelocity - (velocities[columnIndex] ?? 0)) * ease
    let next = (offsets[columnIndex] ?? 0) + velocities[columnIndex] * delta
    next = ((next % meta.copyHeight) + meta.copyHeight) % meta.copyHeight
    offsets[columnIndex] = next
    track.style.transform = `translate3d(0, ${-next}px, 0)`
  })

  columnItems.value.forEach((column, columnIndex) => {
    const meta = columnMeta.value[columnIndex]
    if (!meta) return
    const count = items.value.length
    column.forEach((_, itemIndex) => {
      const tile = tracks.value[columnIndex]?.children[itemIndex] as HTMLElement | undefined
      if (!tile || !count) return
      tile.style.setProperty('--dw-preview-scale', `${fit}`)
    })
  })
  frame = requestAnimationFrame(render)
}

function activate(id: string, column: number) {
  activeId.value = id
  hoveredColumn = column
}

function release() {
  activeId.value = null
  hoveredColumn = -1
}

function pointerMove(event: PointerEvent) {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  pointer = { x: (event.clientX - bounds.left) / bounds.width - 0.5, y: (event.clientY - bounds.top) / bounds.height - 0.5 }
  const target = event.target as HTMLElement | null
  const tile = target?.closest<HTMLElement>('[data-tile-id]')
  if (tile) activate(tile.dataset.tileId ?? '', Number(tile.dataset.column ?? -1))
}

function pointerEnter() {
  wallHovered = true
}

function pointerLeave() {
  wallHovered = false
  pointer = { x: 0, y: 0 }
  release()
}

function resetMeasurements() {
  offsets.splice(0, offsets.length, ...columnMeta.value.map((meta, index) => meta.copyHeight * ((index * 0.37) % 1)))
  velocities.splice(0, velocities.length, ...columnItems.value.map(() => 0))
}

function updateResponsiveColumns(width: number) {
  const next = width < 520 ? Math.min(3, props.columns) : width < 1180 ? Math.min(4, props.columns) : props.columns
  if (responsiveColumns.value !== next) responsiveColumns.value = next
}

function stop() {
  cancelAnimationFrame(frame)
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  motionQuery?.removeEventListener('change', updateReduced)
}

function updateReduced(event: MediaQueryListEvent | MediaQueryList) {
  reduced.value = event.matches
}

watch([columnMeta, columnItems], resetMeasurements, { flush: 'post' })

onMounted(() => {
  if (!root.value || !items.value.length) return
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  updateReduced(motionQuery)
  motionQuery.addEventListener('change', updateReduced)
  resizeObserver = new ResizeObserver(([entry]) => {
    containerHeight.value = entry.contentRect.height || 600
    updateResponsiveColumns(entry.contentRect.width)
  })
  resizeObserver.observe(root.value)
  intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting }, { threshold: 0.02 })
  intersectionObserver.observe(root.value)
  updateResponsiveColumns(root.value.getBoundingClientRect().width)
  resetMeasurements()
  frame = requestAnimationFrame(render)
})

onBeforeUnmount(stop)
</script>

<template>
  <div ref="root" class="drift-wall" :class="{ 'drift-wall--reduced': reduced }" :style="cssVars" role="group" aria-label="人气单品展览" @pointermove="pointerMove" @pointerenter="pointerEnter" @pointerleave="pointerLeave">
    <div ref="plane" class="drift-wall__plane">
      <div v-for="(column, columnIndex) in columnItems" :key="`column-${columnIndex}`" class="drift-wall__column">
        <div :ref="element => { if (element) tracks[columnIndex] = element as HTMLElement }" class="drift-wall__track">
          <template v-for="copyIndex in columnMeta[columnIndex]?.copies ?? 0" :key="`copy-${columnIndex}-${copyIndex}`">
            <template v-for="(item, itemIndex) in column" :key="`${columnIndex}-${copyIndex}-${itemIndex}`">
              <a v-if="item.href" :href="item.href" class="drift-wall__tile" :class="{ 'is-active': activeId === `${columnIndex}-${copyIndex}-${itemIndex}` }" :data-tile-id="`${columnIndex}-${copyIndex}-${itemIndex}`" :data-column="columnIndex" target="_blank" rel="noreferrer noopener" @focus="activate(`${columnIndex}-${copyIndex}-${itemIndex}`, columnIndex)" @blur="release">
                <span class="drift-wall__inner"><img :src="item.image" :alt="item.title" loading="lazy" decoding="async" draggable="false" /><span class="drift-wall__veil" /><span class="drift-wall__caption"><b>{{ item.category }}</b><small>{{ item.title }}</small></span></span>
              </a>
              <div v-else class="drift-wall__tile" :class="{ 'is-active': activeId === `${columnIndex}-${copyIndex}-${itemIndex}` }" :data-tile-id="`${columnIndex}-${copyIndex}-${itemIndex}`" :data-column="columnIndex" tabindex="0" role="img" :aria-label="`${item.category}：${item.title}`" @focus="activate(`${columnIndex}-${copyIndex}-${itemIndex}`, columnIndex)" @blur="release">
                <span class="drift-wall__inner"><img :src="item.image" :alt="item.title" loading="lazy" decoding="async" draggable="false" /><span class="drift-wall__veil" /><span class="drift-wall__caption"><b>{{ item.category }}</b><small>{{ item.title }}</small></span></span>
              </div>
            </template>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drift-wall { position: relative; width: 100%; height: 100%; overflow: hidden; perspective: var(--dw-perspective, 1200px); perspective-origin: 50% 50%; isolation: isolate; -webkit-mask-image: radial-gradient(ellipse 78% 84% at 50% 48%, #000 var(--dw-edge), transparent 100%), linear-gradient(to top, #000 var(--dw-edge), transparent 100%); -webkit-mask-composite: source-in; mask-image: radial-gradient(ellipse 78% 84% at 50% 48%, #000 var(--dw-edge), transparent 100%), linear-gradient(to top, #000 var(--dw-edge), transparent 100%); mask-composite: intersect; }
.drift-wall__plane { position: absolute; top: 50%; left: 50%; display: flex; transform-style: preserve-3d; transform-origin: 50% 50%; will-change: transform; }
.drift-wall__column { position: relative; width: calc(var(--dw-tile-w) + var(--dw-gap)); transform-style: preserve-3d; }
.drift-wall__track { display: flex; flex-direction: column; transform-style: preserve-3d; will-change: transform; }
.drift-wall__tile { position: relative; display: block; width: 100%; height: calc(var(--dw-tile-h) + var(--dw-gap)); flex: 0 0 auto; outline: none; color: inherit; text-decoration: none; transform-style: preserve-3d; }
.drift-wall__inner { position: absolute; inset: calc(var(--dw-gap) / 2); display: block; overflow: hidden; border: 1px solid rgba(255,255,255,.26); border-radius: var(--dw-radius); background: #161412; opacity: var(--dw-dim); transform: translateZ(0); pointer-events: none; transition: transform .42s cubic-bezier(.22,1,.36,1), opacity .42s cubic-bezier(.22,1,.36,1), box-shadow .42s cubic-bezier(.22,1,.36,1); }
.drift-wall__tile img { display: block; width: 100%; height: 100%; object-fit: cover; filter: grayscale(var(--dw-gray)) saturate(.9); user-select: none; -webkit-user-drag: none; transition: filter .42s cubic-bezier(.22,1,.36,1); }
.drift-wall__veil { position: absolute; inset: 0; background: var(--dw-overlay); opacity: .36; transition: opacity .42s cubic-bezier(.22,1,.36,1); }
.drift-wall__caption { position: absolute; right: 10px; bottom: 8px; left: 10px; display: grid; gap: 2px; color: #fffdf8; text-shadow: 0 1px 8px rgba(0,0,0,.45); opacity: 0; transform: translateY(4px); transition: opacity .25s ease, transform .25s ease; }
.drift-wall__caption b { font-size: 10px; letter-spacing: .08em; }
.drift-wall__caption small { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.drift-wall__tile.is-active .drift-wall__inner, .drift-wall__tile:focus-visible .drift-wall__inner { opacity: 1; transform: translateZ(var(--dw-lift)); box-shadow: 0 24px 60px -18px rgba(0,0,0,.72); }
.drift-wall__tile.is-active img, .drift-wall__tile:focus-visible img { filter: grayscale(0) saturate(1.05); }
.drift-wall__tile.is-active .drift-wall__veil, .drift-wall__tile:focus-visible .drift-wall__veil { opacity: .04; }
.drift-wall__tile.is-active .drift-wall__caption, .drift-wall__tile:focus-visible .drift-wall__caption { opacity: 1; transform: translateY(0); }
.drift-wall__tile:focus-visible .drift-wall__inner { box-shadow: 0 24px 60px -18px rgba(0,0,0,.72), 0 0 0 2px rgba(255,255,255,.88); }
.drift-wall--reduced .drift-wall__plane, .drift-wall--reduced .drift-wall__track { will-change: auto; }
</style>
