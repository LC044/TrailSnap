<template>
  <div class="df-page space-y-5">
    <header><RouterLink to="/daily-frame" class="text-sm text-primary-600 dark:text-primary-400">← 返回日历和作品</RouterLink><h1 class="mt-2 text-2xl font-bold">{{ work?.settings.title || '一日一帧影片' }}</h1></header>
    <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }} <button type="button" class="underline" @click="load">重新加载</button></p>
    <section v-if="work" class="df-panel space-y-4">
      <div class="flex flex-wrap justify-between gap-2"><span class="text-primary-600 dark:text-primary-400">{{ workStatus(work.status) }}</span><span class="text-sm text-gray-500 dark:text-gray-400">{{ work.settings.start_date }} — {{ work.settings.end_date }}</span></div>
      <video v-if="url && work.file_available" :src="url" controls playsinline preload="metadata" class="mx-auto max-h-[65vh] w-full rounded-xl bg-black" @error="playbackFailed" />
      <div v-else class="flex min-h-60 flex-col items-center justify-center rounded-xl bg-gray-50 px-5 text-center dark:bg-gray-800">
        <Film class="mb-4 h-12 w-12 text-primary-500" />
        <p>{{ work.error || (work.status === 'missing' ? '作品文件不可用，可以重新生成。' : workStatus(work.status)) }}</p>
        <p v-if="active" class="mt-2 text-sm text-gray-500 dark:text-gray-400">已处理 {{ work.processed_items }}/{{ work.duration }} 个瞬间，可离开页面，任务会继续。</p>
      </div>
      <p class="text-sm text-gray-500 dark:text-gray-400">{{ work.duration }} 个瞬间 · {{ work.duration }} 秒 · {{ work.settings.orientation === 'portrait' ? '竖屏 9:16' : '横屏 16:9' }} · 静音</p>
      <p class="text-xs text-gray-500 dark:text-gray-400">生成时间：{{ work.created_at.slice(0, 16).replace('T', ' ') }}。删除源照片不会同步删除已经生成的作品。</p>
      <p v-if="work.calendar_changed" class="text-sm text-amber-700 dark:text-amber-300">日历已更新，这部影片保留生成时的内容，可以重新制作。</p>
      <div class="flex flex-wrap gap-2">
        <button v-if="work.file_available" type="button" class="df-primary" :disabled="busy" @click="download">{{ busy ? '准备下载…' : '下载 MP4' }}</button>
        <button v-if="active" type="button" class="df-button" :disabled="busy" @click="cancel">取消生成</button>
        <button v-if="['failed', 'cancelled', 'missing'].includes(work.status)" type="button" class="df-primary" :disabled="busy" @click="retry">重试生成</button>
        <RouterLink :to="remakeRoute" class="df-button">重新制作</RouterLink>
        <button type="button" class="df-button" :disabled="busy" @click="remove">删除作品</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Film } from 'lucide-vue-next'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { filmFilename, workStatus } from '@/utils/dailyFrame'
import type { DailyFilmWork } from '@/types/dailyFrame'
import './daily-frame.css'

const route = useRoute(), router = useRouter()
const id = String(route.params.id)
const work = ref<DailyFilmWork | null>(null), url = ref(''), error = ref(''), busy = ref(false)
const active = computed(() => !!work.value && ['queued', 'processing'].includes(work.value.status))
const remakeRoute = computed(() => ({ path: '/daily-frame/create', query: work.value ? { start: work.value.settings.start_date, end: work.value.settings.end_date } : {} }))
let timer: ReturnType<typeof setTimeout> | undefined, mounted = true, loading = false
const controller = new AbortController()
async function load() {
  if (loading || !mounted) return
  clearTimeout(timer); loading = true; error.value = ''
  try {
    const result = await dailyFrameApi.work(id)
    if (!mounted) return
    work.value = result
    if (result.file_available && !url.value) url.value = await dailyFrameApi.playbackUrl(id)
    if (['queued', 'processing'].includes(result.status)) timer = setTimeout(() => void load(), 2500)
  } catch (err) { if (mounted) error.value = dailyFrameError(err) } finally { loading = false }
}
async function download() {
  if (!work.value) return
  busy.value = true
  try {
    const blob = await dailyFrameApi.file(id, true, controller.signal)
    const link = document.createElement('a'), objectUrl = URL.createObjectURL(blob)
    link.href = objectUrl; link.download = filmFilename(work.value.settings.start_date, work.value.duration, work.value.settings.title)
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(objectUrl), 30000)
  } catch (err) { error.value = dailyFrameError(err) } finally { busy.value = false }
}
async function retry() {
  busy.value = true; url.value = ''
  try { work.value = await dailyFrameApi.retry(id); await load() }
  catch (err) { error.value = dailyFrameError(err) } finally { busy.value = false }
}
async function cancel() {
  busy.value = true
  try { await dailyFrameApi.cancel(id); await load() } catch (err) { error.value = dailyFrameError(err) } finally { busy.value = false }
}
async function remove() {
  try { await ElMessageBox.confirm('删除这部影片及生成文件；每日选帧和原照片仍保留。', '删除作品', { type: 'warning' }) } catch { return }
  busy.value = true
  try { await dailyFrameApi.delete(id); await router.push('/daily-frame') }
  catch (err) { error.value = dailyFrameError(err) } finally { busy.value = false }
}
function playbackFailed() { url.value = ''; error.value = '播放凭证可能已过期，请重新加载作品。' }
onMounted(() => void load())
onBeforeUnmount(() => { mounted = false; clearTimeout(timer); controller.abort() })
</script>
