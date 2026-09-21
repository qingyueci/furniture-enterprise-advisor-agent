<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import * as THREE from 'three'

const props = withDefaults(defineProps<{
  variation?: 0 | 1 | 2 | 3
  pixelRatioProp?: number
  shapeSize?: number
  roundness?: number
  borderSize?: number
  circleSize?: number
  circleEdge?: number
  followPointer?: boolean
}>(), {
  variation: 0,
  pixelRatioProp: 1,
  shapeSize: 0.5,
  roundness: 0.5,
  borderSize: 0.05,
  circleSize: 0.5,
  circleEdge: 1,
  followPointer: true,
})

const root = ref<HTMLElement | null>(null)
const failed = ref(false)
const uniformsRef = { current: null as null | Record<string, { value: unknown }> }
let teardown: (() => void) | null = null

const vertexShader = `
varying vec2 v_texcoord;
void main() {
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  v_texcoord = uv;
}`

const fragmentShader = `
varying vec2 v_texcoord;
uniform vec2 u_mouse;
uniform vec2 u_resolution;
uniform float u_pixelRatio;
uniform float u_shapeSize;
uniform float u_roundness;
uniform float u_borderSize;
uniform float u_circleSize;
uniform float u_circleEdge;
#ifndef PI
#define PI 3.1415926535897932384626433832795
#endif
#ifndef TWO_PI
#define TWO_PI 6.2831853071795864769252867665590
#endif
#ifndef VAR
#define VAR 0
#endif
vec2 coord(in vec2 p) {
  p = p / u_resolution.xy;
  if (u_resolution.x > u_resolution.y) {
    p.x *= u_resolution.x / u_resolution.y;
    p.x += (u_resolution.y - u_resolution.x) / u_resolution.y / 2.0;
  } else {
    p.y *= u_resolution.y / u_resolution.x;
    p.y += (u_resolution.x - u_resolution.y) / u_resolution.x / 2.0;
  }
  p -= 0.5;
  p *= vec2(-1.0, 1.0);
  return p;
}
#define st0 coord(gl_FragCoord.xy)
#define mx coord(u_mouse * u_pixelRatio)
float sdRoundRect(vec2 p, vec2 b, float r) {
  vec2 d = abs(p - 0.5) * 4.2 - b + vec2(r);
  return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)) - r;
}
float sdCircle(in vec2 st, in vec2 center) { return length(st - center) * 2.0; }
float sdPoly(in vec2 p, in float w, in int sides) {
  float a = atan(p.x, p.y) + PI;
  float r = TWO_PI / float(sides);
  float d = cos(floor(0.5 + a / r) * r - a) * length(max(abs(p), 0.0));
  return d * 2.0 - w;
}
float aastep(float threshold, float value) {
  float afwidth = length(vec2(dFdx(value), dFdy(value))) * 0.70710678118654757;
  return smoothstep(threshold - afwidth, threshold + afwidth, value);
}
float fill(in float x) { return 1.0 - aastep(0.0, x); }
float fill(float x, float size, float edge) { return 1.0 - smoothstep(size - edge, size + edge, x); }
float strokeAA(float x, float size, float w, float edge) {
  float afwidth = length(vec2(dFdx(x), dFdy(x))) * 0.70710678;
  float d = smoothstep(size - edge - afwidth, size + edge + afwidth, x + w * 0.5)
    - smoothstep(size - edge - afwidth, size + edge + afwidth, x - w * 0.5);
  return clamp(d, 0.0, 1.0);
}
void main() {
  vec2 st = st0 + 0.5;
  vec2 posMouse = mx * vec2(1.0, -1.0) + 0.5;
  float sdfCircle = fill(sdCircle(st, posMouse), u_circleSize, u_circleEdge);
  float sdf;
  if (VAR == 0) {
    sdf = sdRoundRect(st, vec2(u_shapeSize), u_roundness);
    sdf = strokeAA(sdf, 0.0, u_borderSize, sdfCircle) * 4.0;
  } else if (VAR == 1) {
    sdf = sdCircle(st, vec2(0.5));
    sdf = fill(sdf, 0.6, sdfCircle) * 1.2;
  } else if (VAR == 2) {
    sdf = sdCircle(st, vec2(0.5));
    sdf = strokeAA(sdf, 0.58, 0.02, sdfCircle) * 4.0;
  } else {
    sdf = sdPoly(st - vec2(0.5, 0.45), 0.3, 3);
    sdf = fill(sdf, 0.05, sdfCircle) * 1.4;
  }
  gl_FragColor = vec4(vec3(1.0), sdf);
}`

watchEffect(() => {
  const uniforms = uniformsRef.current
  if (!uniforms) return
  uniforms.u_pixelRatio.value = props.pixelRatioProp
  uniforms.u_shapeSize.value = props.shapeSize
  uniforms.u_roundness.value = props.roundness
  uniforms.u_borderSize.value = props.borderSize
  uniforms.u_circleSize.value = props.circleSize
  uniforms.u_circleEdge.value = props.circleEdge
})

onMounted(() => {
  const mount = root.value
  if (!mount) return
  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
  } catch {
    failed.value = true
    return
  }
  renderer.setClearColor(0x000000, 0)
  renderer.domElement.style.display = 'block'
  renderer.domElement.style.width = '100%'
  renderer.domElement.style.height = '100%'
  mount.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  const camera = new THREE.OrthographicCamera()
  camera.position.z = 1
  const mouse = new THREE.Vector2(-9999, -9999)
  const dampedMouse = new THREE.Vector2()
  const resolution = new THREE.Vector2()
  const geometry = new THREE.PlaneGeometry(1, 1)
  const material = new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms: {
      u_mouse: { value: dampedMouse }, u_resolution: { value: resolution }, u_pixelRatio: { value: props.pixelRatioProp },
      u_shapeSize: { value: props.shapeSize }, u_roundness: { value: props.roundness }, u_borderSize: { value: props.borderSize },
      u_circleSize: { value: props.circleSize }, u_circleEdge: { value: props.circleEdge },
    },
    defines: { VAR: props.variation },
    transparent: true,
  })
  const quad = new THREE.Mesh(geometry, material)
  scene.add(quad)
  uniformsRef.current = material.uniforms

  let active = true
  let width = 1
  let height = 1
  let frame = 0
  let lastTime = performance.now()
  const resize = () => {
    if (!active) return
    width = Math.max(1, mount.clientWidth)
    height = Math.max(1, mount.clientHeight)
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    renderer.setPixelRatio(dpr)
    renderer.setSize(width, height, false)
    camera.left = -width / 2; camera.right = width / 2; camera.top = height / 2; camera.bottom = -height / 2
    camera.updateProjectionMatrix()
    quad.scale.set(width, height, 1)
    resolution.set(width, height).multiplyScalar(dpr)
    material.uniforms.u_pixelRatio.value = props.pixelRatioProp
  }
  const localPoint = (event: MouseEvent) => {
    const rect = mount.getBoundingClientRect()
    if (!rect.width || !rect.height || event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
      mouse.set(-9999, -9999)
      return
    }
    if (props.followPointer) {
      mouse.set(event.clientX - rect.left, event.clientY - rect.top)
    } else {
      mouse.set(rect.width / 2, rect.height / 2)
    }
  }
  const onPointerMove = (event: MouseEvent) => localPoint(event)
  document.addEventListener('pointermove', onPointerMove, { passive: true })
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(mount)
  resize()
  const update = (now: number) => {
    if (!active) return
    const dt = Math.min(0.05, Math.max(0, (now - lastTime) / 1000))
    lastTime = now
    if (mouse.x < -1000 || dampedMouse.x < -1000) {
      dampedMouse.copy(mouse)
    } else {
      dampedMouse.x = THREE.MathUtils.damp(dampedMouse.x, mouse.x, 8, dt)
      dampedMouse.y = THREE.MathUtils.damp(dampedMouse.y, mouse.y, 8, dt)
    }
    renderer.render(scene, camera)
    frame = requestAnimationFrame(update)
  }
  frame = requestAnimationFrame(update)
  teardown = () => {
    active = false
    cancelAnimationFrame(frame)
    resizeObserver.disconnect()
    document.removeEventListener('pointermove', onPointerMove)
    if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    geometry.dispose(); material.dispose(); renderer.dispose(); renderer.forceContextLoss(); uniformsRef.current = null
  }
})

onBeforeUnmount(() => teardown?.())
</script>

<template>
  <div ref="root" class="shape-blur" aria-hidden="true">
    <span v-if="failed" class="shape-blur__fallback" />
  </div>
</template>

<style scoped>
.shape-blur { position: relative; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
.shape-blur canvas { width: 100%; height: 100%; }
.shape-blur__fallback { position: absolute; inset: 10%; border: 1px solid rgba(38,35,31,.12); border-radius: 16px; filter: blur(8px); }
</style>
