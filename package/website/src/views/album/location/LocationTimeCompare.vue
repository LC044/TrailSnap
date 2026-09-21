<template>
  <div class="time-compare min-h-screen bg-gray-950 text-white">
    <header class="fixed inset-x-0 top-0 z-30 flex h-16 items-center justify-between border-b border-white/10 bg-gray-950/85 px-3 backdrop-blur-xl md:px-6">
      <div class="flex min-w-0 items-center gap-2 md:gap-3">
        <button
          type="button"
          class="grid h-10 w-10 shrink-0 place-items-center rounded-full text-white/80 transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950"
          aria-label="返回"
          @click="goBack"
        >
          <ArrowLeft class="h-5 w-5" />
        </button>
        <div class="min-w-0">
          <div class="truncate text-sm font-semibold md:text-base">{{ summary?.location_name || '地点时光对照' }}</div>
          <div class="text-xs text-white/60">{{ summary?.match_type === 'nearby_gps' ? `相似视角优先 · GPS ${summary.radius_m} 米内` : '相似视角优先' }}</div>
        </div>
      </div>

      <div class="hidden text-base font-semibold md:block">时光对照</div>

      <div class="flex items-center gap-2">
        <div class="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/75 sm:flex">
          <LockKeyhole class="h-3.5 w-3.5" />
          仅显示城市
        </div>
        <button
          v-if="summary?.eligible"
          type="button"
          class="grid h-10 w-10 place-items-center rounded-xl border border-white/15 text-white/85 transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          :aria-label="animating ? '暂停变化动画' : '播放变化动画'"
          :title="animating ? '暂停变化动画' : '播放变化动画'"
          @click="toggleRevealAnimation"
        >
          <Pause v-if="animating" class="h-4 w-4" />
          <Play v-else class="h-4 w-4" />
        </button>
        <button
          v-if="summary?.eligible"
          type="button"
          class="flex min-h-10 items-center gap-2 rounded-xl bg-primary-500 px-3 text-sm font-semibold text-white shadow-lg shadow-primary-500/20 transition hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950 md:px-4"
          :disabled="exporting"
          @click="exportArtwork"
        >
          <LoaderCircle v-if="exporting" class="h-4 w-4 animate-spin" />
          <Download v-else class="h-4 w-4" />
          <span class="hidden sm:inline">{{ exporting ? '正在生成' : '生成对比作品' }}</span>
        </button>
      </div>
    </header>

    <main class="flex min-h-screen flex-col px-3 pb-5 pt-20 md:px-6 md:pb-6 md:pt-24">
      <div v-if="loading" class="flex flex-1 flex-col items-center justify-center gap-3 text-white/60" role="status">
        <LoaderCircle class="h-8 w-8 animate-spin text-primary-500" />
        <span>正在整理这里的时间记录…</span>
      </div>

      <section v-else-if="loadError" class="mx-auto flex max-w-md flex-1 flex-col items-center justify-center text-center">
        <div class="mb-4 grid h-16 w-16 place-items-center rounded-full bg-white/5"><Images class="h-8 w-8 text-white/40" /></div>
        <h1 class="text-xl font-semibold">暂时无法打开时光对照</h1>
        <p class="mt-2 text-sm leading-6 text-white/60">{{ loadError }}</p>
        <button class="mt-6 rounded-xl bg-primary-500 px-5 py-2.5 text-sm font-semibold hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950" @click="loadSummary">重新加载</button>
      </section>

      <section v-else-if="summary && !summary.eligible" class="mx-auto flex max-w-lg flex-1 flex-col items-center justify-center text-center">
        <div class="mb-5 grid h-20 w-20 place-items-center rounded-full border border-white/10 bg-white/5"><CalendarDays class="h-9 w-9 text-primary-400" /></div>
        <h1 class="text-2xl font-semibold">{{ unavailableTitle }}</h1>
        <p class="mt-3 text-sm leading-6 text-white/60">{{ unavailableDescription }}</p>
        <button class="mt-7 rounded-xl border border-white/15 px-5 py-2.5 text-sm font-medium hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950" @click="goBack">返回地点相册</button>
      </section>

      <template v-else-if="summary?.eligible && leftPhoto && rightPhoto">
        <div class="mx-auto mb-3 grid w-full max-w-7xl grid-cols-[1fr_auto_1fr] items-center gap-2 px-1 text-sm md:mb-4 md:px-8">
          <button
            type="button"
            class="justify-self-start rounded-lg px-2 py-1 text-left transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            :class="activeSide === 'left' ? 'text-white' : 'text-white/60'"
            @click="activateSide('left')"
          >
            <span class="block text-xs text-white/40">较早</span>
            <span class="font-medium">{{ formatDate(leftPhoto.photo_time) }}</span>
          </button>
          <div class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/75 md:px-4">{{ gapLabel }}</div>
          <button
            type="button"
            class="justify-self-end rounded-lg px-2 py-1 text-right transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            :class="activeSide === 'right' ? 'text-white' : 'text-white/60'"
            @click="activateSide('right')"
          >
            <span class="block text-xs text-white/40">较晚</span>
            <span class="font-medium">{{ formatDate(rightPhoto.photo_time) }}</span>
          </button>
        </div>

        <div
          ref="compareCanvas"
          class="relative mx-auto min-h-0 w-full max-w-7xl flex-1 touch-none select-none overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl"
          @dblclick="sliderPosition = 50"
          @pointerdown="startDragging"
        >
          <img :src="leftImage?.url" alt="较早照片" class="absolute inset-0 h-full w-full object-contain" draggable="false" />
          <img
            :src="rightImage?.url"
            alt="较晚照片"
            class="absolute inset-0 h-full w-full object-contain"
            :style="{ clipPath: `inset(0 0 0 ${sliderPosition}%)` }"
            draggable="false"
          />

          <div class="pointer-events-none absolute inset-y-0 z-10 w-0.5 bg-primary-500 shadow-[0_0_18px_rgba(var(--theme-rgb),0.75)]" :style="{ left: `${sliderPosition}%` }">
            <button
              type="button"
              role="slider"
              aria-label="调整今昔照片分割线"
              aria-valuemin="5"
              aria-valuemax="95"
              :aria-valuenow="Math.round(sliderPosition)"
              class="pointer-events-auto absolute left-1/2 top-1/2 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 cursor-col-resize place-items-center rounded-full border-2 border-white bg-primary-500 text-white shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950"
              @keydown.left.prevent="nudgeSlider(-5)"
              @keydown.right.prevent="nudgeSlider(5)"
              @pointerdown.stop="startDragging"
            >
              <ChevronsLeftRight class="h-5 w-5" />
            </button>
          </div>

          <div class="pointer-events-none absolute inset-x-0 bottom-0 flex justify-between bg-gradient-to-t from-black/70 to-transparent p-3 pt-12 md:p-5 md:pt-20">
            <button type="button" class="pointer-events-auto flex items-center gap-2 rounded-xl border border-white/20 bg-black/45 px-3 py-2 text-xs font-medium backdrop-blur-md hover:bg-black/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 md:text-sm" @pointerdown.stop @click.stop="openPhotoPicker('left')">
              <Images class="h-4 w-4" />更换照片
            </button>
            <button type="button" class="pointer-events-auto flex items-center gap-2 rounded-xl border border-white/20 bg-black/45 px-3 py-2 text-xs font-medium backdrop-blur-md hover:bg-black/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 md:text-sm" @pointerdown.stop @click.stop="openPhotoPicker('right')">
              <Images class="h-4 w-4" />更换照片
            </button>
          </div>
        </div>

        <div class="mx-auto mt-4 w-full max-w-7xl rounded-2xl border border-white/10 bg-gray-900/80 px-3 py-3 backdrop-blur md:px-5 md:py-4">
          <div class="mb-2 flex items-center justify-between gap-3 px-1">
            <div>
              <div class="text-xs font-semibold text-white/80">访问时间轴</div>
              <div class="mt-0.5 text-[10px] text-white/40">先点上方日期选择一侧，再点这里的日期快速切换</div>
            </div>
            <div class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] text-white/55">
              当前更换{{ activeSide === 'left' ? '较早' : '较晚' }}侧
            </div>
          </div>
          <div class="overflow-x-auto">
            <div class="flex min-w-max items-start md:min-w-0">
              <button
                v-for="item in summary.visits"
                :key="item.date"
                type="button"
                class="group relative flex min-w-20 flex-1 flex-col items-center gap-1 px-2 pb-1 pt-4 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                :class="visitClass(item.date)"
                @click="selectVisit(item.date)"
              >
                <span class="absolute left-0 right-0 top-1.5 h-px bg-gray-700 group-first:left-1/2 group-last:right-1/2"></span>
                <span class="absolute top-0 h-4 w-4 rounded-full border-2 border-gray-900" :class="visitDotClass(item.date)"></span>
                <span class="font-semibold">{{ formatVisitLabel(item.date) }}</span>
                <span class="text-[10px] text-white/40">{{ item.photo_count }} 张</span>
              </button>
            </div>
          </div>
        </div>
      </template>
    </main>

    <Transition name="drawer">
      <div v-if="pickerOpen" class="fixed inset-0 z-40" @click.self="closePicker">
        <div class="absolute inset-0 bg-black/55 backdrop-blur-sm" @click="closePicker"></div>
        <aside class="absolute inset-x-0 bottom-0 max-h-[72vh] overflow-hidden rounded-t-3xl border-t border-white/10 bg-gray-900 shadow-2xl md:inset-y-0 md:left-auto md:w-[420px] md:max-h-none md:rounded-none md:border-l md:border-t-0">
          <div class="flex items-center justify-between border-b border-white/10 px-4 py-4">
            <div>
              <h2 class="font-semibold">正在更换{{ pickerSide === 'left' ? '较早' : '较晚' }}照片</h2>
              <p class="mt-0.5 text-xs text-white/60">全部候选 · 按与另一侧的匹配分排序 · {{ pickerPhotos.length }} 张</p>
            </div>
            <button type="button" class="grid h-9 w-9 place-items-center rounded-full text-white/75 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" aria-label="关闭照片选择器" @click="closePicker"><X class="h-5 w-5" /></button>
          </div>
          <div v-if="pickerLoading" class="flex h-48 items-center justify-center"><LoaderCircle class="h-7 w-7 animate-spin text-primary-500" /></div>
          <div v-else class="grid max-h-[calc(72vh-73px)] grid-cols-3 gap-2 overflow-y-auto p-3 md:max-h-[calc(100vh-73px)]">
            <button
              v-for="photo in pickerPhotos"
              :key="photo.id"
              type="button"
              class="relative aspect-square overflow-hidden rounded-xl border-2 bg-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              :class="selectedPhotoId === photo.id ? 'border-primary-500' : 'border-transparent hover:border-gray-500'"
              @click="choosePhoto(photo)"
            >
              <img :src="photoImage(photo).thumbnail" alt="" class="h-full w-full object-cover" loading="lazy" />
              <span class="absolute inset-x-0 bottom-0 bg-black/65 px-1.5 py-1 text-[10px] text-white/80">{{ formatDate(photo.photo_time) }}</span>
            </button>
          </div>
        </aside>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CalendarDays, ChevronsLeftRight, Download, Images, LoaderCircle, LockKeyhole, Pause, Play, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { locationService } from '@/api/location'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { AlbumImage, Photo } from '@/types/album'
import type { TimeCompareSummary } from '@/types/location'

type CompareSide = 'left' | 'right'

const route = useRoute()
const router = useRouter()
const sceneId = computed(() => {
  const value = String(route.params.sceneId || '')
  return value && value !== 'gps' ? value : undefined
})
const sourcePhotoId = computed(() => typeof route.query.photoId === 'string' ? route.query.photoId : undefined)

const summary = ref<TimeCompareSummary | null>(null)
const loading = ref(true)
const loadError = ref('')
const leftPhoto = ref<Photo | null>(null)
const rightPhoto = ref<Photo | null>(null)
const activeSide = ref<CompareSide>('right')
const sliderPosition = ref(50)
const compareCanvas = ref<HTMLElement | null>(null)
const photoCache = new Map<string, Photo[]>()

const pickerOpen = ref(false)
const pickerSide = ref<CompareSide>('right')
const pickerPhotos = ref<Photo[]>([])
const pickerLoading = ref(false)
const exporting = ref(false)

const leftImage = computed<AlbumImage | null>(() => leftPhoto.value ? mapPhotoToImage(leftPhoto.value) : null)
const rightImage = computed<AlbumImage | null>(() => rightPhoto.value ? mapPhotoToImage(rightPhoto.value) : null)
const leftYear = computed(() => yearOf(leftPhoto.value))
const rightYear = computed(() => yearOf(rightPhoto.value))
const leftVisitDate = computed(() => dateKey(leftPhoto.value))
const rightVisitDate = computed(() => dateKey(rightPhoto.value))
const selectedPhotoId = computed(() => pickerSide.value === 'left' ? leftPhoto.value?.id : rightPhoto.value?.id)
const gapLabel = computed(() => {
  if (!leftPhoto.value?.photo_time || !rightPhoto.value?.photo_time) return ''
  const days = Math.max(1, Math.round(Math.abs(new Date(rightPhoto.value.photo_time).getTime() - new Date(leftPhoto.value.photo_time).getTime()) / 86400000))
  if (days >= 365) return `相隔 ${Math.round(days / 365)} 年`
  if (days >= 30) return `相隔 ${Math.round(days / 30)} 个月`
  return `相隔 ${days} 天`
})
const unavailableTitle = computed(() => {
  if (summary.value?.reason === 'precise_location_required') return '缺少位置信息'
  if (summary.value?.reason === 'similar_view_required') return '还没有相似视角'
  return '还缺一次重访'
})
const unavailableDescription = computed(() => {
  if (summary.value?.reason === 'precise_location_required') return '这张照片没有有效 GPS 信息，暂时无法寻找附近的旧照片。'
  if (summary.value?.reason === 'similar_view_required') return '附近虽然有其他年份的照片，但画面差异较大，暂时不适合生成时光对照。'
  return '这里目前只有一个拍摄年份。以后再次来到这里，新的照片就会出现在时光对照中。'
})

function yearOf(photo: Photo | null) {
  if (!photo?.photo_time) return 0
  return new Date(photo.photo_time).getFullYear()
}

function dateKey(photo: Photo | null) {
  return photo?.photo_time ? photo.photo_time.slice(0, 10) : ''
}

function formatVisitLabel(value: string) {
  if (!value) return ''
  const [year, month, day] = value.split('-')
  return `${year.slice(2)}.${month}.${day}`
}

function formatDate(value?: string) {
  if (!value) return '未知日期'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知日期'
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`
}

const photoImage = (photo: Photo) => mapPhotoToImage(photo)

async function comparisonPhotos(referencePhotoId?: string, visitDate?: string) {
  const cacheKey = `${visitDate || 'all'}:${referencePhotoId || ''}`
  const cached = photoCache.get(cacheKey)
  if (cached) return cached
  const photos = await locationService.getTimeComparePhotos(
    {
      sceneId: summary.value?.scene_id || sceneId.value,
      photoId: summary.value?.source_photo_id || sourcePhotoId.value,
      referencePhotoId,
    },
    visitDate,
    0,
    500,
  )
  const candidates = referencePhotoId ? photos.filter(photo => photo.id !== referencePhotoId) : photos
  photoCache.set(cacheKey, candidates)
  return candidates
}

async function loadSummary() {
  loading.value = true
  loadError.value = ''
  photoCache.clear()
  let shouldAnimate = false
  try {
    const data = await locationService.getTimeCompareSummary({ sceneId: sceneId.value, photoId: sourcePhotoId.value })
    summary.value = data
    if (!data.eligible || !data.first_photo || !data.latest_photo) return

    leftPhoto.value = data.first_photo
    rightPhoto.value = data.latest_photo
    shouldAnimate = true
  } catch (error) {
    console.error(error)
    loadError.value = '地点不存在、无权访问，或照片位置仍需确认。'
  } finally {
    loading.value = false
  }
  if (shouldAnimate) {
    await nextTick()
    playRevealAnimation()
  }
}

function activateSide(side: CompareSide) {
  activeSide.value = side
}

async function selectVisit(visitDate: string) {
  const otherVisitDate = activeSide.value === 'left' ? rightVisitDate.value : leftVisitDate.value
  if (visitDate === otherVisitDate) {
    ElMessage.info('请选择另一个拍摄日进行对照')
    return
  }
  try {
    const referencePhoto = activeSide.value === 'left' ? rightPhoto.value : leftPhoto.value
    const photos = await comparisonPhotos(referencePhoto?.id, visitDate)
    if (!photos.length) return
    const chosen = photos[0]
    if (activeSide.value === 'left') leftPhoto.value = chosen
    else rightPhoto.value = chosen
    normalizeSides()
  } catch (error) {
    console.error(error)
    ElMessage.error('加载该年份照片失败')
  }
}

function normalizeSides() {
  if (!leftPhoto.value || !rightPhoto.value || new Date(leftPhoto.value.photo_time || 0) <= new Date(rightPhoto.value.photo_time || 0)) return
  const previousLeft = leftPhoto.value
  leftPhoto.value = rightPhoto.value
  rightPhoto.value = previousLeft
  activeSide.value = activeSide.value === 'left' ? 'right' : 'left'
}

async function openPhotoPicker(side: CompareSide) {
  pickerOpen.value = true
  pickerSide.value = side
  activeSide.value = side
  pickerLoading.value = true
  try {
    const referencePhoto = side === 'left' ? rightPhoto.value : leftPhoto.value
    pickerPhotos.value = await comparisonPhotos(referencePhoto?.id)
  } catch (error) {
    console.error(error)
    ElMessage.error('加载照片失败')
    closePicker()
  } finally {
    pickerLoading.value = false
  }
}

function choosePhoto(photo: Photo) {
  if (pickerSide.value === 'left') leftPhoto.value = photo
  else rightPhoto.value = photo
  normalizeSides()
  closePicker()
}

function closePicker() {
  pickerOpen.value = false
}

function visitClass(visitDate: string) {
  if (visitDate === leftVisitDate.value || visitDate === rightVisitDate.value) return 'text-white'
  return 'text-white/60 hover:text-white/80'
}

function visitDotClass(visitDate: string) {
  if (visitDate === rightVisitDate.value) return 'bg-primary-500 shadow-[0_0_12px_rgba(var(--theme-rgb),0.8)]'
  if (visitDate === leftVisitDate.value) return 'bg-white'
  return 'bg-gray-600 group-hover:bg-gray-400'
}

let dragging = false
const animating = ref(false)
let animationFrame = 0
let animationStartedAt = 0

function stopRevealAnimation() {
  animating.value = false
  if (animationFrame) cancelAnimationFrame(animationFrame)
  animationFrame = 0
}

function toggleRevealAnimation() {
  if (animating.value) {
    stopRevealAnimation()
    return
  }
  playRevealAnimation()
}

function playRevealAnimation() {
  stopRevealAnimation()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    sliderPosition.value = 50
    ElMessage.info('已根据系统设置减少动态效果')
    return
  }
  sliderPosition.value = 5
  animating.value = true
  animationStartedAt = performance.now()
  const duration = 3200
  const tick = (now: number) => {
    const progress = Math.min(1, (now - animationStartedAt) / duration)
    const eased = 1 - Math.pow(1 - progress, 3)
    sliderPosition.value = 5 + eased * 90
    if (progress < 1 && animating.value) {
      animationFrame = requestAnimationFrame(tick)
    } else {
      stopRevealAnimation()
      sliderPosition.value = 50
    }
  }
  animationFrame = requestAnimationFrame(tick)
}

function updateSlider(clientX: number) {
  const rect = compareCanvas.value?.getBoundingClientRect()
  if (!rect?.width) return
  sliderPosition.value = Math.min(95, Math.max(5, ((clientX - rect.left) / rect.width) * 100))
}

function startDragging(event: PointerEvent) {
  stopRevealAnimation()
  dragging = true
  updateSlider(event.clientX)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', stopDragging, { once: true })
}

function onPointerMove(event: PointerEvent) {
  if (dragging) updateSlider(event.clientX)
}

function stopDragging() {
  dragging = false
  window.removeEventListener('pointermove', onPointerMove)
}

function nudgeSlider(amount: number) {
  sliderPosition.value = Math.min(95, Math.max(5, sliderPosition.value + amount))
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/album/location')
}

async function exportArtwork() {
  if (!leftPhoto.value || !rightPhoto.value || !summary.value) return
  exporting.value = true
  try {
    await document.fonts?.ready
    const [leftBlob, rightBlob] = await Promise.all([
      locationService.getPhotoBlob(leftPhoto.value.id),
      locationService.getPhotoBlob(rightPhoto.value.id),
    ])
    const [leftBitmap, rightBitmap] = await Promise.all([createImageBitmap(leftBlob), createImageBitmap(rightBlob)])
    const canvas = document.createElement('canvas')
    canvas.width = 1800
    canvas.height = 1200
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#030712'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    drawContained(ctx, leftBitmap, 50, 170, 840, 850)
    drawContained(ctx, rightBitmap, 910, 170, 840, 850)

    ctx.fillStyle = '#ffffff'
    ctx.font = '600 44px system-ui, sans-serif'
    ctx.fillText('时光对照', 50, 78)
    ctx.font = '700 30px system-ui, sans-serif'
    ctx.fillText(summary.value.city || '', 50, 124)
    ctx.textAlign = 'right'
    ctx.font = '500 28px system-ui, sans-serif'
    ctx.fillText(gapLabel.value, 1750, 104)

    ctx.textAlign = 'left'
    ctx.font = '600 28px system-ui, sans-serif'
    ctx.fillText(formatDate(leftPhoto.value.photo_time), 50, 1085)
    ctx.textAlign = 'right'
    ctx.fillText(formatDate(rightPhoto.value.photo_time), 1750, 1085)
    ctx.textAlign = 'center'
    ctx.fillStyle = '#9ca3af'
    ctx.font = '400 22px system-ui, sans-serif'
    ctx.fillText('精确位置已隐藏', 900, 1140)

    leftBitmap.close()
    rightBitmap.close()
    const result = await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Canvas export failed')), 'image/png'))
    const url = URL.createObjectURL(result)
    const link = document.createElement('a')
    const safeName = (summary.value.location_name || '地点').replace(/[\\/:*?"<>|]/g, '-')
    link.href = url
    link.download = `${safeName}-时光对照-${leftYear.value}-${rightYear.value}.png`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('对比作品已生成，精确位置未包含在作品中')
  } catch (error) {
    console.error(error)
    ElMessage.error('生成作品失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

function drawContained(ctx: CanvasRenderingContext2D, image: ImageBitmap, x: number, y: number, width: number, height: number) {
  ctx.fillStyle = '#111827'
  ctx.fillRect(x, y, width, height)
  const scale = Math.min(width / image.width, height / image.height)
  const drawWidth = image.width * scale
  const drawHeight = image.height * scale
  ctx.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight)
}

onMounted(loadSummary)
onBeforeUnmount(() => {
  stopRevealAnimation()
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', stopDragging)
})
</script>

<style scoped>
.time-compare {
  background:
    radial-gradient(circle at 50% 0%, rgba(var(--theme-rgb), 0.08), transparent 34rem),
    #030712;
}

.drawer-enter-active,
.drawer-leave-active { transition: opacity 180ms ease; }
.drawer-enter-active aside,
.drawer-leave-active aside { transition: transform 220ms ease; }
.drawer-enter-from,
.drawer-leave-to { opacity: 0; }
.drawer-enter-from aside,
.drawer-leave-to aside { transform: translateY(100%); }

@media (min-width: 768px) {
  .drawer-enter-from aside,
  .drawer-leave-to aside { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active,
  .drawer-leave-active,
  .drawer-enter-active aside,
  .drawer-leave-active aside { transition: none; }
}
</style>
