<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useData } from 'vitepress'
// Use the product renderer and province-adaptive photo allocation, not a map texture.
import { buildRegionGeometry, filterRegionFeatures, findRegionAt, shortenRegionName, type RegionGeometry } from '../../../../website/src/utils/mapPuzzle/geoPath'
import { computeBBox, createProjector } from '../../../../website/src/utils/mapPuzzle/geoProjection'
import { assignPhotos, buildGrid } from '../../../../website/src/utils/mapPuzzle/gridFill'
import { renderPuzzle, setupCanvas, LIGHT_THEME, DARK_THEME } from '../../../../website/src/utils/mapPuzzle/renderer'

const { isDark } = useData()
const host = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const state = ref<'loading' | 'ready' | 'error'>('loading')
const active = ref<string | null>(null)
const regionCount = ref(0)
const images = new Map<string, HTMLImageElement>()
const pools = new Map<string, string[]>()
const controller = new AbortController()
let features: any[] = []
let geometries: RegionGeometry[] = []
let observer: ResizeObserver | undefined
let frame = 0
let disposed = false
let started = false

function paint() {
  frame = 0
  if (!host.value || !canvas.value || !features.length || disposed) return
  const width = Math.round(host.value.clientWidth), height = Math.round(host.value.clientHeight)
  if (!width || !height) return
  const selected = active.value ? features.filter(f => f.properties.name === active.value) : features
  const projection = createProjector(computeBBox(selected, .05), width, height, width < 500 ? 12 : 28)
  geometries = selected.map(f => buildRegionGeometry(f, projection, .05))
  const counts = new Map([...pools].map(([name, photos]) => [name, photos.length]))
  const cells = buildGrid(geometries, { targetCount: active.value ? 60 : 600, minCellSize: 9, photoCounts: counts, skipEmptyRegions: true })
  const ctx = setupCanvas(canvas.value, width, height)
  if (!ctx) return
  const css = getComputedStyle(host.value)
  renderPuzzle({ ctx, width, height, geometries, cells, assignments: assignPhotos(cells, pools), resolveImage: id => images.get(id), options: {
    showLabel: Boolean(active.value), litRegions: new Set(pools.keys()),
    theme: { ...(isDark.value ? DARK_THEME : LIGHT_THEME), background: null, stroke: css.getPropertyValue('--paper').trim(), unlitStroke: css.getPropertyValue('--line').trim(), glow: null },
  } })
}
function schedule() { if (!disposed && !frame) frame = requestAnimationFrame(paint) }
function choose(event: MouseEvent) {
  if (!canvas.value) return
  if (active.value) { active.value = null; schedule(); return }
  const rect = canvas.value.getBoundingClientRect()
  const region = findRegionAt(event.clientX - rect.left, event.clientY - rect.top, geometries)
  if (region && pools.has(region.name)) { active.value = region.name; schedule() }
}
async function load() {
  state.value = 'loading'
  try {
    const [geoResponse, sampleResponse] = await Promise.all([
      fetch('/showcase/province-geo.json', { signal: controller.signal }),
      fetch('/showcase/puzzle-sample.json', { signal: controller.signal }),
    ])
    if (!geoResponse.ok || !sampleResponse.ok) throw Error('Sample unavailable')
    const [geo, sample] = await Promise.all([geoResponse.json(), sampleResponse.json()])
    if (disposed) return
    features = filterRegionFeatures(geo.features)
    const names = new Map<string, string>()
    for (const feature of features) { const name = feature.properties.name; names.set(name, name); names.set(shortenRegionName(name), name) }
    await Promise.all(sample.regions.map(async (region: { name: string; photos: string[] }) => {
      const name = names.get(region.name) || names.get(shortenRegionName(region.name))
      if (!name || !region.photos.length) return
      const loaded = await Promise.all(region.photos.map(async (src: string) => {
        const image = new Image(); image.src = src
        try { await image.decode(); if (!disposed) images.set(src, image); return src } catch { return null }
      }))
      if (!disposed) pools.set(name, loaded.filter((src): src is string => Boolean(src)))
    }))
    if (disposed) return
    regionCount.value = [...pools.values()].filter(photos => photos.length).length
    state.value = 'ready'; schedule()
  } catch { if (!disposed) state.value = 'error' }
}
onMounted(() => {
  observer = new ResizeObserver(() => {
    if (!host.value?.clientWidth || !host.value.clientHeight) return
    if (!started) { started = true; void load() } else schedule()
  })
  if (host.value) observer.observe(host.value)
})
watch(isDark, schedule)
onBeforeUnmount(() => { disposed = true; controller.abort(); observer?.disconnect(); cancelAnimationFrame(frame); images.clear() })
</script>

<template>
  <div ref="host" class="footprint-puzzle">
    <canvas ref="canvas" role="img" :aria-label="active ? `${active}的照片拼图` : '演示相册的全国足迹拼图，照片按省份排列'" @click="choose" />
    <p v-if="state === 'loading'" class="puzzle-state" role="status">正在拼起旅途中的照片…</p>
    <div v-if="state === 'error'" class="puzzle-state" role="alert">拼图暂时无法加载 <button type="button" @click="load">重试</button></div>
    <button v-if="active" class="puzzle-back" type="button" @click="active = null; schedule()">← 全国足迹</button>
    <span v-if="state === 'ready'" class="puzzle-source">{{ active || `${regionCount} 个省级地区` }} · 演示相册快照</span>
  </div>
</template>

<style scoped>
.footprint-puzzle{position:absolute;inset:0;background:var(--bg);overflow:hidden}
canvas{display:block;width:100%;height:100%;cursor:pointer}
.puzzle-state{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:12px;color:var(--muted);font-size:13px}
.puzzle-back{position:absolute;top:14px;left:14px;background:var(--paper);border:1px solid var(--line);border-radius:7px;padding:8px 12px;font-size:12px;color:var(--primary)}
.puzzle-source{position:absolute;right:16px;bottom:10px;color:var(--muted);font-size:10px;pointer-events:none}
button:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
</style>
