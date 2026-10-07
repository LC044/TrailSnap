<template>
  <div class="df-page space-y-5">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div><BackButton to="/daily-frame" label="返回日历" /><h1 class="mt-2 text-2xl font-bold">制作一日一帧影片</h1></div>
      <span class="text-sm text-gray-500 dark:text-gray-400">每天一秒 · 静音 · 按日期播放</span>
    </header>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{{ error }}</p>
    <p v-if="store.settings && !store.settings.export.available" class="rounded-xl bg-amber-50 p-4 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">{{ store.settings.export.reason }}</p>
    <div v-if="ready" class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="df-panel space-y-4">
        <div class="flex items-center justify-between"><h2 class="font-semibold">影片预览</h2><span class="text-xs text-gray-500 dark:text-gray-400">{{ previewUrl ? '低清预览，与导出采用相同排版' : '先更新预览，查看真实成片效果' }}</span></div>
        <div ref="previewBox" class="mx-auto flex items-center justify-center overflow-hidden rounded-xl" :class="form.orientation === 'portrait' ? 'aspect-[9/16] w-full max-w-[min(340px,33.75vh)]' : 'aspect-video w-full max-w-[106.66vh]'" :style="{ backgroundColor: form.background }">
          <video v-if="previewUrl" ref="player" :src="previewUrl" controls playsinline muted preload="metadata" class="h-full w-full object-contain" @timeupdate="onTime" @error="previewPlaybackFailed" />
          <div v-else-if="firstFrameUrl && !renderingPreview" class="relative h-full w-full">
            <video v-if="selectedFrame?.mode === 'motion'" ref="firstVideo" :src="firstFrameUrl" muted playsinline preload="metadata" class="h-full w-full" :class="form.fit === 'cover' ? 'object-cover' : 'object-contain'" @loadedmetadata="seekFirstVideo" @error="firstFrameFailed" />
            <img v-else :src="firstFrameUrl" alt="当前片段的画面与排版预览" class="h-full w-full" :class="form.fit === 'cover' ? 'object-cover' : 'object-contain'" @error="firstFrameFailed" />
            <div v-if="form.show_date || (form.show_caption && selectedFrame?.caption)" class="absolute inset-x-[7%] bottom-[7%] rounded-md bg-black/65 px-2 py-1 text-center text-white" :style="{ fontSize: `${previewWidth * 42 / (form.orientation === 'portrait' ? 1080 : 1920)}px`, lineHeight: '1.43' }">
              <p v-if="form.show_date">{{ selectedFrame?.day.replaceAll('-', '.') }}</p><p v-if="form.show_caption && selectedFrame?.caption" class="mx-auto max-w-[94%] break-all">{{ selectedFrame.caption }}</p>
            </div>
          </div>
          <div v-else class="px-7 text-center text-sm" :class="form.background === '#f9fafb' ? 'text-gray-700 dark:text-gray-700' : 'text-white'">
            <Film class="mx-auto mb-3 h-10 w-10 opacity-60" />
            <p>{{ renderingPreview ? workStatus(previewWork?.status || 'queued') : firstFrameLoading ? '正在加载当前片段…' : '每一天的代表瞬间，将在这里串成一部影片' }}</p>
            <p v-if="renderingPreview" class="mt-2">已处理 {{ previewWork?.processed_items || 0 }}/{{ previewWork?.duration || composition?.duration || 0 }} 个瞬间</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button class="df-button" type="button" :disabled="busy || renderingPreview || !canCreate" @click="generate(true)">{{ previewUrl ? '重新更新预览' : '更新预览' }}</button>
          <button v-if="renderingPreview && previewWork" type="button" class="df-button" @click="cancelPreview">取消预览生成</button>
          <button v-if="composition?.snapshot.frames.length" class="df-button" type="button" :disabled="renderingPreview || busy" @click="editCurrent">编辑 {{ selectedFrame?.day }}</button>
        </div>
        <p v-if="previewWork?.error" class="text-sm text-red-600 dark:text-red-400">{{ previewWork.error }}</p>
        <div v-if="composition" class="flex gap-2 overflow-x-auto pb-2" aria-label="按日期排序的影片片段">
          <button v-for="(frame, index) in composition.snapshot.frames" :key="frame.day" type="button" class="w-20 shrink-0 rounded-lg border-2 p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :class="selectedIndex === index ? 'border-primary-500' : 'border-transparent'" :aria-label="`第 ${index + 1} 秒，${frame.day}`" :aria-pressed="selectedIndex === index" @click="seek(index)">
            <img :src="thumbnailUrl(frame.photo_id)" :alt="frame.day" class="aspect-square w-full rounded object-cover" loading="lazy" />
            <span class="mt-1 block text-center text-[10px] text-gray-500 dark:text-gray-400">{{ frame.day.slice(5) }}</span>
          </button>
        </div>
        <p v-if="selectedFrame?.caption" class="text-sm text-gray-600 dark:text-gray-300">{{ selectedFrame.caption }}</p>
        <p v-if="!composition?.duration && !updating" class="py-5 text-center text-gray-500 dark:text-gray-400">先选至少一个瞬间，再回来制作影片。<RouterLink to="/daily-frame" class="ml-2 text-primary-600 dark:text-primary-400">去选帧</RouterLink></p>
      </section>
      <aside class="df-panel space-y-4 lg:self-start">
        <h2 class="font-semibold">影片设置</h2>
        <div class="flex flex-wrap gap-2"><button type="button" class="df-button" @click="useMonth">这个月</button><button type="button" class="df-button" @click="useYear">这一年</button></div>
        <label class="block text-sm">开始日期<input v-model="form.start_date" type="date" min="1900-01-01" :max="today" class="df-input mt-1" /></label>
        <label class="block text-sm">结束日期<input v-model="form.end_date" type="date" :min="form.start_date" :max="today" class="df-input mt-1" /></label>
        <p class="text-xs text-gray-500 dark:text-gray-400">包含首尾日期，最多 366 天；空缺日期自然跳过。</p>
        <label class="block text-sm">标题<input v-model="form.title" maxlength="40" class="df-input mt-1" /></label>
        <label class="block text-sm">画幅<select v-model="form.orientation" class="df-input mt-1"><option value="portrait">竖屏 9:16</option><option value="landscape">横屏 16:9</option></select></label>
        <label class="block text-sm">画面适配<select v-model="form.fit" class="df-input mt-1"><option value="contain">完整画面（保留全部构图）</option><option value="cover">填满画面（居中裁切）</option></select></label>
        <div class="flex flex-wrap gap-4 text-sm"><label><input v-model="form.show_date" type="checkbox" class="mr-2 accent-[var(--theme-primary)]" />显示日期</label><label><input v-model="form.show_caption" type="checkbox" class="mr-2 accent-[var(--theme-primary)]" />显示一句话</label></div>
        <div v-if="composition?.invalid.length" class="space-y-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <p>{{ composition.invalid.length }} 天素材失效：</p>
          <RouterLink v-for="item in composition.invalid" :key="item.day" :to="`/daily-frame?day=${item.day}`" class="block underline">{{ item.day }} · {{ item.reason }}</RouterLink>
          <label class="block"><input v-model="form.skip_invalid" type="checkbox" class="mr-2 accent-[var(--theme-primary)]" />本次跳过失效素材</label>
        </div>
        <div class="rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <p v-if="updating" role="status">正在更新选帧…</p>
          <p v-else-if="composition">{{ rangeDays }} 天范围 · {{ composition.duration }} 个瞬间<br />{{ composition.empty_days }} 天未选 · 预计 {{ composition.duration }} 秒</p>
          <p v-else>请选择有效日期范围。</p>
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">导出 1080p MP4，静音，无片头片尾；日期和文字与预览一致。</p>
        <button type="button" class="df-primary w-full" :disabled="busy || renderingPreview || !canCreate" @click="generate(false)">{{ busy ? '提交中…' : '生成影片' }}</button>
      </aside>
    </div>
    <FrameEditor v-if="editorDay" v-model="editorVisible" :day="editorDay" @saved="refreshAfterEdit" />
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Film } from 'lucide-vue-next'
import { injectTheme } from '@/composables/useTheme'
import { useDailyFrameStore } from '@/stores/dailyFrameStore'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { monthRange, workStatus } from '@/utils/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { DailyFilmSettings, DailyFilmComposition, DailyFilmWork } from '@/types/dailyFrame'
import FrameEditor from './FrameEditor.vue'
import './daily-frame.css'

const route = useRoute(), router = useRouter(), store = useDailyFrameStore()
const theme = injectTheme()
const ready = ref(false), busy = ref(false), updating = ref(false), error = ref(''), today = ref('')
const form = reactive<DailyFilmSettings>({ start_date: '', end_date: '', title: '', orientation: 'portrait', fit: 'contain', show_date: true, show_caption: true, background: '#111827', skip_invalid: false })
const composition = ref<DailyFilmComposition | null>(null), previewWork = ref<DailyFilmWork | null>(null), previewUrl = ref('')
const selectedIndex = ref(0), player = ref<HTMLVideoElement | null>(null)
const firstFrameUrl = ref(''), firstFrameLoading = ref(false), firstVideo = ref<HTMLVideoElement | null>(null)
const previewBox = ref<HTMLElement | null>(null), previewWidth = ref(340)
let firstFrameRequest = 0, firstFrameController: AbortController | null = null, resizeObserver: ResizeObserver | undefined
const editorDay = ref(''), editorVisible = ref(false)
const selectedFrame = computed(() => composition.value?.snapshot.frames[selectedIndex.value])
const rangeDays = computed(() => Math.round((Date.parse(form.end_date) - Date.parse(form.start_date)) / 86400000) + 1)
const renderingPreview = computed(() => !!previewWork.value && ['queued', 'processing'].includes(previewWork.value.status))
const canCreate = computed(() => !!store.settings?.export.available && !updating.value && !!composition.value?.duration
  && (!composition.value.invalid.length || form.skip_invalid) && form.title.trim().length > 0)
let requestId = 0, previewEpoch = 0, mounted = true
let refreshTimer: ReturnType<typeof setTimeout> | undefined, pollTimer: ReturnType<typeof setTimeout> | undefined
function background() { return theme.isDarkMode.value ? '#111827' : '#f9fafb' }

function useMonth() {
  const month = /^\d{4}-\d{2}$/.test(String(route.query.month || '')) ? String(route.query.month) : store.month
  const range = monthRange(month)
  form.start_date = range[0]; form.end_date = range[1] > today.value ? today.value : range[1]
  form.title = `${month.replace('-', ' 年 ')} 月 · 一日一帧`
}
function useYear() {
  const year = /^\d{4}$/.test(String(route.query.year || '')) ? String(route.query.year) : store.month.slice(0, 4)
  form.start_date = `${year}-01-01`; form.end_date = `${year}-12-31` > today.value ? today.value : `${year}-12-31`
  form.title = `${year} 年 · 一日一帧`
}
function invalidate() {
  requestId++; previewEpoch++; clearTimeout(pollTimer); previewUrl.value = ''; selectedIndex.value = 0
  if (previewWork.value) void dailyFrameApi.delete(previewWork.value.id).catch(() => {})
  previewWork.value = null; composition.value = null
}
async function updateComposition() {
  const request = ++requestId; updating.value = true; error.value = ''
  try {
    const result = await dailyFrameApi.composition({ ...form })
    if (request === requestId && mounted) composition.value = result
  } catch (err) { if (request === requestId && mounted) error.value = dailyFrameError(err) }
  finally { if (request === requestId) updating.value = false }
}
async function pollPreview(id: string, epoch: number) {
  try {
    const work = await dailyFrameApi.work(id)
    if (!mounted || epoch !== previewEpoch) return
    previewWork.value = work
    if (work.status === 'ready') {
      const url = await dailyFrameApi.playbackUrl(id)
      if (mounted && epoch === previewEpoch) previewUrl.value = url
    } else if (['queued', 'processing'].includes(work.status)) pollTimer = setTimeout(() => void pollPreview(id, epoch), 2000)
  } catch (err) { if (mounted && epoch === previewEpoch) error.value = dailyFrameError(err) }
}
async function generate(isPreview: boolean) {
  if (!canCreate.value || busy.value) return
  busy.value = true; error.value = ''
  const epoch = previewEpoch
  try {
    const work = await dailyFrameApi.create({ ...form }, composition.value!.fingerprint, isPreview)
    if (isPreview) {
      if (epoch === previewEpoch && mounted) { previewWork.value = work; await pollPreview(work.id, epoch) }
      else void dailyFrameApi.delete(work.id).catch(() => {})
    }
    else await router.push(`/daily-frame/works/${work.id}`)
  } catch (err) { const message = dailyFrameError(err); await updateComposition(); error.value = message }
  finally { busy.value = false }
}
async function cancelPreview() { if (previewWork.value) { await dailyFrameApi.cancel(previewWork.value.id); previewWork.value.status = 'cancelled'; clearTimeout(pollTimer) } }
function seek(index: number) { selectedIndex.value = index; if (player.value) player.value.currentTime = index }
function onTime() { if (player.value && composition.value) selectedIndex.value = Math.min(Math.floor(player.value.currentTime), composition.value.duration - 1) }
function editCurrent() { if (selectedFrame.value) { editorDay.value = selectedFrame.value.day; editorVisible.value = true } }
async function refreshAfterEdit() { invalidate(); await updateComposition(); await store.refresh() }
function previewPlaybackFailed() { previewUrl.value = ''; error.value = '预览播放失败，请更新预览后重试。' }
function firstFrameFailed() { error.value = '当前片段预览无法读取，请更新预览或更换素材。' }
function seekFirstVideo() { if (firstVideo.value && selectedFrame.value) firstVideo.value.currentTime = selectedFrame.value.start_seconds }
async function loadFirstFrame() {
  const request = ++firstFrameRequest
  firstFrameController?.abort(); firstFrameController = new AbortController()
  if (firstFrameUrl.value.startsWith('blob:')) URL.revokeObjectURL(firstFrameUrl.value)
  firstFrameUrl.value = ''; firstFrameLoading.value = false
  const frame = selectedFrame.value
  if (!frame || previewUrl.value) return
  firstFrameLoading.value = true
  try {
    const url = frame.mode === 'motion' ? await dailyFrameApi.sourceUrl(frame.photo_id, 'motion')
      : URL.createObjectURL(await dailyFrameApi.source(frame.photo_id, 'still', firstFrameController.signal))
    if (request === firstFrameRequest && mounted) firstFrameUrl.value = url
    else if (url.startsWith('blob:')) URL.revokeObjectURL(url)
  } catch (err) { if (request === firstFrameRequest && mounted) error.value = dailyFrameError(err) }
  finally { if (request === firstFrameRequest) firstFrameLoading.value = false }
}
watch([selectedFrame, previewUrl], () => void loadFirstFrame())
watch(previewBox, box => {
  resizeObserver?.disconnect()
  if (box) {
    resizeObserver = new ResizeObserver(entries => { previewWidth.value = entries[0].contentRect.width })
    resizeObserver.observe(box)
  }
})
watch(form, () => {
  if (!ready.value) return
  invalidate(); updating.value = true; clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => void updateComposition(), 350)
}, { deep: true })
watch([theme.isDarkMode, theme.currentTheme], () => { form.background = background() })
onMounted(async () => {
  try {
    const config = await store.initialize(); today.value = config.today!
    form.background = background()
    if (route.query.year) useYear(); else useMonth()
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(route.query.start || '')) && /^\d{4}-\d{2}-\d{2}$/.test(String(route.query.end || ''))) {
      form.start_date = String(route.query.start); form.end_date = String(route.query.end)
      form.title = `${form.start_date} — ${form.end_date} · 一日一帧`
    }
    ready.value = true; await updateComposition()
  } catch (err) { error.value = dailyFrameError(err) }
})
onBeforeUnmount(() => { invalidate(); mounted = false; firstFrameRequest++; firstFrameController?.abort(); if (firstFrameUrl.value.startsWith('blob:')) URL.revokeObjectURL(firstFrameUrl.value); resizeObserver?.disconnect(); clearTimeout(refreshTimer); clearTimeout(pollTimer) })
</script>
