<template>
  <div class="absolute inset-0 pointer-events-none" data-testid="panorama-photo">
    <div v-if="active" class="absolute inset-0 pointer-events-auto bg-black" @click.stop @mousedown.stop @touchstart.stop @touchmove.stop @touchend.stop @wheel.stop>
      <div ref="container" class="h-full w-full" />
    </div>
    <div v-if="busy" class="absolute inset-0 flex items-center justify-center" role="status">
      <span class="inline-flex items-center gap-2 rounded-full bg-black/60 px-4 py-2 text-sm text-white">
        <LoaderCircle class="h-4 w-4 animate-spin" />正在加载全景…
      </span>
    </div>
    <div v-else-if="message" class="absolute inset-x-4 top-20 flex justify-center" @click.stop @mousedown.stop @touchstart.stop>
      <div class="ts-liquid-glass ts-glass-toolbar flex max-w-full items-center gap-2 rounded-full px-3 py-1 pointer-events-auto">
        <span role="status" class="text-sm">{{ message }}</span>
        <button type="button" class="ts-glass-button shrink-0" aria-label="重试加载全景" title="重试加载全景" @click="loadInfo"><RotateCcw class="h-4 w-4" /></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { LoaderCircle, RotateCcw } from 'lucide-vue-next'
import type { Viewer } from '@photo-sphere-viewer/core'
import { panoramaApi, type PanoramaInfo } from '@/api/panorama'
import { textureGeometry, canUseHighResolution } from '@/utils/panorama'

const props = defineProps<{ photoId: string }>()
const emit = defineEmits<{
  active: [value: boolean]
  state: [value: { available: boolean; busy: boolean; high: boolean; allowHigh: boolean }]
  tap: []
}>()
const container = ref<HTMLElement>()
const info = ref<PanoramaInfo | null>(null)
const viewer = shallowRef<Viewer>()
const active = ref(false), busy = ref(false), high = ref(false), message = ref('')
const maxTexture = ref(0)
let generation = 0, disposed = false, imageUrl: string | null = null
let controller: AbortController | null = null
let deadline: ReturnType<typeof setTimeout> | undefined
const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4
const allowHigh = computed(() => !!info.value && canUseHighResolution(info.value.geometry?.fullWidth || info.value.width, info.value.geometry?.fullHeight || info.value.height, maxTexture.value, memory))
watch(() => ({ available: !!info.value?.projection, busy: busy.value, high: high.value, allowHigh: allowHigh.value }), state => emit('state', state), { immediate: true })

function clearDeadline() { clearTimeout(deadline); deadline = undefined }
function release() {
  generation++
  clearDeadline()
  controller?.abort()
  controller = null
  const previous = viewer.value
  viewer.value = undefined
  previous?.destroy()
  if (imageUrl) URL.revokeObjectURL(imageUrl)
  imageUrl = null
}
function fallback(text: string) {
  release()
  active.value = false
  busy.value = false
  message.value = text
  emit('active', false)
}
function beginOperation() {
  release()
  const current = generation
  controller = new AbortController()
  busy.value = true
  message.value = ''
  deadline = setTimeout(() => {
    if (!disposed && current === generation) fallback('全景加载超时，已切换平面查看')
  }, 25000)
  return { current, signal: controller.signal }
}
function initialView() {
  const data = info.value?.geometry
  return { yaw: `${data?.initialHeading ?? data?.poseHeading ?? 0}deg`, pitch: `${data?.initialPitch ?? 0}deg` }
}
function resetView() { viewer.value?.rotate(initialView()); viewer.value?.zoom(50) }

async function renderPanorama() {
  if (!active.value || !info.value?.geometry) return
  const { current, signal } = beginOperation()
  try {
    const [library, blob] = await Promise.all([
      import('@photo-sphere-viewer/core'), panoramaApi.image(props.photoId, high.value, signal),
      import('@photo-sphere-viewer/core/index.css'),
    ])
    await nextTick()
    if (disposed || current !== generation) return
    if (!container.value) throw new Error('全景容器不可用')
    imageUrl = URL.createObjectURL(blob)
    const geometry = info.value.geometry
    const panoData = textureGeometry(geometry, info.value.width, info.value.height, high.value)
    if (panoData.fullWidth > maxTexture.value || panoData.fullHeight > maxTexture.value) throw new Error('全景纹理超过设备限制')
    viewer.value = new library.Viewer({
      container: container.value, adapter: library.EquirectangularAdapter.withConfig({ useXmpData: false }),
      navbar: false, keyboard: false, panorama: undefined, panoData,
      defaultYaw: initialView().yaw, defaultPitch: initialView().pitch,
      minFov: 30, maxFov: 100, defaultZoomLvl: 50, loadingTxt: '正在加载全景…',
    })
    container.value.querySelector('canvas')?.addEventListener('webglcontextlost', () => {
      if (current === generation) fallback('全景显示中断，已切换平面查看')
    }, { once: true })
    viewer.value.addEventListener('click', () => emit('tap'))
    await viewer.value.setPanorama(imageUrl, { panoData, transition: false })
    if (current !== generation || disposed) return
    clearDeadline()
    busy.value = false
  } catch {
    if (!disposed && current === generation) fallback('全景加载失败，已切换平面查看')
  }
}

async function loadInfo() {
  const { current, signal } = beginOperation()
  active.value = false
  emit('active', false)
  try {
    const result = await panoramaApi.info(props.photoId, signal)
    if (disposed || current !== generation) return
    info.value = result
    clearDeadline()
    active.value = !!result.projection && maxTexture.value >= 4096
    emit('active', active.value)
    busy.value = false
    if (active.value) await renderPanorama()
    else if (result.projection) message.value = '当前设备无法显示全景，已使用平面查看'
  } catch {
    if (!disposed && current === generation) fallback('全景信息读取失败，可继续平面查看')
  }
}
async function toggleMode() {
  if (busy.value) return
  if (!info.value) { await loadInfo(); return }
  if (!active.value && maxTexture.value < 4096) { message.value = '当前设备无法显示全景'; return }
  active.value = !active.value
  emit('active', active.value)
  if (active.value) await renderPanorama()
  else { release(); message.value = ''; busy.value = false }
}
function toggleHigh() { if (allowHigh.value && active.value && !busy.value) { high.value = !high.value; void renderPanorama() } }
onMounted(() => {
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2')
    if (gl) { maxTexture.value = gl.getParameter(gl.MAX_TEXTURE_SIZE); gl.getExtension('WEBGL_lose_context')?.loseContext() }
  } catch { /* Flat viewing remains available. */ }
  void loadInfo()
})
defineExpose({ toggleMode, toggleHigh, toggleFullscreen: () => viewer.value?.toggleFullscreen(), loadInfo,
  zoomIn: () => viewer.value?.zoom(Math.min(100, (viewer.value?.getZoomLevel() || 0) + 10)),
  zoomOut: () => viewer.value?.zoom(Math.max(0, (viewer.value?.getZoomLevel() || 0) - 10)), resetView })
onBeforeUnmount(() => { disposed = true; release(); emit('active', false) })
</script>
