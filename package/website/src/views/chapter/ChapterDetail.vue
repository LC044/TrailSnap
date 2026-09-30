<template>
  <div class="min-h-full bg-gray-50 px-4 py-5 dark:bg-gray-900 md:px-8 md:py-7">
    <div class="mx-auto max-w-6xl">
      <div class="flex items-center justify-between gap-3"><RouterLink to="/chapters" class="text-sm text-primary-600 dark:text-primary-400">← 人生章节</RouterLink><div v-if="chapter" class="flex gap-2"><RouterLink :to="`/chapters/${chapter.id}/edit${chapter.is_hidden ? '?manage=1' : ''}`" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">编辑</RouterLink><button class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" @click="menuVisible = true">更多</button></div></div>
      <div v-if="loading" class="py-24 text-center text-gray-500 dark:text-gray-400">正在打开章节…</div>
      <template v-else-if="chapter">
        <div v-if="chapter.status === 'candidate'" class="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30"><strong class="text-amber-800 dark:text-amber-200">系统建议 · 待你确认</strong><p class="mt-1 text-sm text-amber-800 dark:text-amber-200">照片只能提供时间和地点线索，章节的意义由你定义。</p><div v-for="(e, index) in chapter.evidence" :key="index" class="mt-3 text-sm text-gray-700 dark:text-gray-300"><p>• {{ e.summary }}</p><div v-if="e.photo_ids?.length" class="mt-2 flex gap-2 overflow-x-auto" aria-label="建议依据照片"><img v-for="id in e.photo_ids" :key="id" :src="thumbnailUrl(id, 'small')" alt="建议依据照片" class="h-16 w-16 shrink-0 rounded object-cover" loading="lazy" /></div></div><div class="mt-4 flex gap-2"><button class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-gray-600" @click="perform('ignore')">忽略</button><button class="rounded-lg bg-primary-500 px-4 py-2 text-sm text-white" @click="perform('confirm')">确认并保存</button></div></div>
        <div v-if="chapter.is_hidden" class="mt-5 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">该章节已隐藏，原照片和记忆仍在各自页面。<button class="ml-2 text-primary-600 dark:text-primary-400" @click="perform('unhide')">恢复显示</button></div>
        <div class="mt-5 rounded-xl bg-[#eee7da] p-2.5 shadow-xl dark:bg-gray-700 lg:p-3">
          <div class="grid overflow-hidden rounded-lg bg-[#fffdf8] text-[#34414a] dark:bg-gray-800 dark:text-gray-100 lg:min-h-[650px] lg:grid-cols-2">
            <section class="border-b border-[#e8e0d3] p-6 dark:border-gray-700 lg:border-b-0 lg:border-r lg:p-9">
              <div class="flex justify-between border-b border-[#e8e0d3] pb-3 text-xs tracking-widest text-gray-500 dark:border-gray-700 dark:text-gray-400"><span>行影集 · 人生章节</span><span>{{ currentYear || '扉页' }} / {{ page * 2 + 1 }}</span></div>
              <template v-if="page === 0">
                <div class="mt-8 rotate-[-1deg] border bg-white p-2 pb-5 shadow-lg dark:border-gray-600 dark:bg-gray-700"><img v-if="chapter.cover_photo_id" :src="thumbnailUrl(chapter.cover_photo_id, 'medium')" :alt="chapter.title" class="aspect-[4/3] w-full object-cover" /><div v-else class="aspect-[4/3] bg-gray-100 dark:bg-gray-600" /><p class="px-2 pt-3 font-serif text-xs text-gray-500 dark:text-gray-300">这段时光的封面，由你选择。</p></div>
                <p class="mt-6 text-xs leading-6 text-gray-500 dark:text-gray-400">按拍摄时间整理影像。照片里的线索，不替你定义经历。</p>
              </template>
              <template v-else>
                <p class="mt-7 text-xs tracking-[0.25em] text-primary-600 dark:text-primary-400">这一年的日记</p><h1 class="mt-3 font-serif text-5xl">{{ currentYear }}</h1>
                <p class="mt-3 text-sm text-gray-500 dark:text-gray-400">这一年保存在本章的影像</p>
                <div class="mt-8 rotate-[-1deg] border bg-white p-2 pb-5 shadow-lg dark:border-gray-600 dark:bg-gray-700"><img v-if="yearPhotos[0]" :src="thumbnailUrl(yearPhotos[0].id, 'medium')" alt="这一年的代表照片" class="aspect-[4/3] w-full object-cover" /><div v-else class="aspect-[4/3] bg-gray-100 dark:bg-gray-600" /><p class="px-2 pt-3 font-serif text-xs text-gray-500 dark:text-gray-300">{{ currentYear }} 年 · {{ yearTotal }} 张影像</p></div>
              </template>
            </section>
            <section class="p-6 lg:p-9" :class="page === 0 ? 'order-first lg:order-none' : ''"><div class="flex justify-between border-b border-[#e8e0d3] pb-3 text-xs tracking-widest text-gray-500 dark:border-gray-700 dark:text-gray-400"><span>CHAPTER</span><span>{{ page * 2 + 2 }}</span></div>
              <template v-if="page === 0"><p class="mt-8 text-xs tracking-[0.2em] text-primary-600 dark:text-primary-400">一段时光 · 一本自己的日记</p><h1 class="mt-5 font-serif text-3xl leading-relaxed">{{ chapter.title }}</h1><p class="mt-3 text-xs text-gray-500 dark:text-gray-400">{{ chapter.start_date }} — {{ chapter.end_date || '至今' }} · {{ chapter.photo_count }} 张影像 · {{ chapter.event_count }} 段事件</p><p class="mt-7 border-t border-[#e8e0d3] pt-6 font-serif text-base leading-9 dark:border-gray-700">{{ chapter.summary || `这一阶段保存了 ${chapter.photo_count} 张影像，包含 ${chapter.event_count} 段已确认记忆。` }}</p><p v-if="!chapter.summary" class="text-xs text-gray-500 dark:text-gray-400">根据照片整理 · 你可以编辑这段简介</p><h2 class="mt-8 border-t border-[#e8e0d3] pt-6 font-serif text-lg dark:border-gray-700">翻开这一章</h2><div class="mt-3 divide-y divide-[#e8e0d3] dark:divide-gray-700"><button v-for="(year, index) in chapter.years" :key="year" class="flex w-full items-center justify-between py-2 text-left text-sm" @click="page = index + 1"><span class="font-serif text-primary-600 dark:text-primary-400">{{ year }}</span><span>查看这一年 →</span></button></div></template>
              <template v-else><p class="mt-8 text-xs tracking-[0.2em] text-primary-600 dark:text-primary-400">照片与事件</p><h2 class="mt-5 font-serif text-xl">{{ currentYear }} 年的画面</h2><p class="mt-4 text-sm leading-8 text-gray-600 dark:text-gray-300">按这一年拍摄的照片排列。没有记录的月份保持空白。</p><div class="mt-7 border-t border-[#e8e0d3] pt-5 dark:border-gray-700"><h3 class="font-serif text-base">已确认的记忆</h3><RouterLink v-for="event in yearEvents" :key="event.id" :to="`/memories/${event.id}`" class="mt-3 block border-b border-[#e8e0d3] py-2 text-sm text-primary-600 dark:border-gray-700 dark:text-primary-400">{{ event.title }}　→</RouterLink><p v-if="!yearEvents.length" class="mt-3 text-xs text-gray-500 dark:text-gray-400">这一年暂无已确认记忆。</p><button v-if="yearEventTotal > yearEvents.length" class="mt-3 text-sm text-primary-600 dark:text-primary-400" @click="loadMoreEvents">查看更多记忆</button></div><div class="mt-7 border-t border-[#e8e0d3] pt-5 dark:border-gray-700"><h3 class="font-serif text-base">这一年的影像</h3><div class="mt-3 grid grid-cols-3 gap-2"><button v-for="(photo, index) in yearPhotos" :key="photo.id" class="aspect-square overflow-hidden rounded" @click="lightboxIndex = index"><img :src="thumbnailUrl(photo.id, 'small')" :alt="photo.filename" class="h-full w-full object-cover" loading="lazy" /></button></div><button v-if="yearTotal > yearPhotos.length" class="mt-3 text-sm text-primary-600 dark:text-primary-400" @click="loadMore">查看更多影像</button></div></template>
            </section>
          </div>
        </div>
        <nav class="mt-5 flex items-center justify-between gap-2" aria-label="日记本翻页"><button class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800" :disabled="page === 0" @click="page--">← 上一页</button><div class="flex max-w-[60%] gap-1 overflow-x-auto"><button class="rounded px-2 py-2 text-xs" :class="page === 0 ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30' : 'text-gray-500 dark:text-gray-400'" @click="page = 0">扉页</button><button v-for="(year, index) in chapter.years" :key="year" class="rounded px-2 py-2 text-xs" :class="page === index + 1 ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30' : 'text-gray-500 dark:text-gray-400'" @click="page = index + 1">{{ year }}</button></div><button class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800" :disabled="page >= chapter.years.length" @click="page++">下一页 →</button></nav>
        <section class="mt-9"><h2 class="font-serif text-xl text-gray-900 dark:text-white">章节索引</h2><div class="mt-4 grid gap-4 md:grid-cols-3"><div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"><h3 class="text-sm font-semibold">一起出现在照片里的人</h3><p class="mt-3 text-sm text-gray-500 dark:text-gray-400">{{ chapter.people.slice(0, 5).map(person => person.name).join(' · ') || '暂无人物线索' }}</p></div><div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"><h3 class="text-sm font-semibold">常被记录的地方</h3><p class="mt-3 text-sm text-gray-500 dark:text-gray-400">{{ chapter.places.slice(0, 3).map(place => place.name).join(' · ') || '暂无地点线索' }}</p></div><div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"><h3 class="text-sm font-semibold">这一阶段的影像</h3><p class="mt-3 text-sm text-gray-500 dark:text-gray-400">共 {{ chapter.photo_count }} 张 · 按年翻阅</p></div></div></section>
      </template>
    </div>
    <PhotoLightbox v-if="lightboxIndex >= 0" :visible="lightboxIndex >= 0" :image="lightboxImages[lightboxIndex] || null" :images="lightboxImages" :current-index="lightboxIndex" :has-prev="lightboxIndex > 0" :has-next="lightboxIndex < lightboxImages.length - 1" @prev="lightboxIndex--" @next="lightboxIndex++" @close="lightboxIndex = -1" />
    <el-dialog v-model="menuVisible" title="章节管理" width="min(92vw, 460px)"><div class="flex flex-col gap-2 text-left"><button v-if="chapter?.status === 'confirmed' || chapter?.status === 'candidate'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="openSplit">拆分章节</button><button v-if="chapter?.status === 'confirmed' || chapter?.status === 'candidate'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="openMerge">合并章节</button><button v-if="chapter?.status === 'confirmed'" class="rounded-lg border border-gray-200 p-3 dark:border-gray-700" @click="perform(chapter.is_hidden ? 'unhide' : 'hide')">{{ chapter.is_hidden ? '恢复显示' : '隐藏章节' }}</button><button class="rounded-lg border border-red-200 p-3 text-red-600" @click="remove">删除章节</button></div></el-dialog>
    <el-dialog v-model="splitVisible" title="拆分章节" width="min(92vw, 520px)"><p class="mb-4 text-sm text-gray-500 dark:text-gray-400">分界日归入后一章。跨界事件可以在两章中出现。</p><div class="space-y-3"><label class="block text-sm">分界日<input v-model="splitForm.split_date" type="date" class="mt-1 w-full rounded border p-2 dark:border-gray-600 dark:bg-gray-800" /></label><label class="block text-sm">前一章名称<input v-model="splitForm.first_title" class="mt-1 w-full rounded border p-2 dark:border-gray-600 dark:bg-gray-800" /></label><label class="block text-sm">后一章名称<input v-model="splitForm.second_title" class="mt-1 w-full rounded border p-2 dark:border-gray-600 dark:bg-gray-800" /></label></div><template #footer><button class="rounded-lg bg-primary-500 px-4 py-2 text-white" @click="splitChapter">确认拆分</button></template></el-dialog>
    <el-dialog v-model="mergeVisible" title="合并章节" width="min(92vw, 520px)"><p class="mb-4 text-sm text-gray-500 dark:text-gray-400">两章将合为连续时间范围，中间时段的影像也会纳入。</p><select v-model="mergeTargetId" class="w-full rounded border p-2 dark:border-gray-600 dark:bg-gray-800"><option value="">选择另一章</option><option v-for="item in mergeOptions" :key="item.id" :value="item.id">{{ item.title }} · {{ item.start_date }}—{{ item.end_date || '至今' }}</option></select><label class="mt-4 block text-sm">新章节名称<input v-model="mergeTitle" class="mt-1 w-full rounded border p-2 dark:border-gray-600 dark:bg-gray-800" /></label><p v-if="mergePreview" class="mt-4 rounded-lg bg-primary-50 p-3 text-sm dark:bg-primary-900/20">合并范围包含 {{ mergePreview.photo_count }} 张影像，两章原有 {{ mergeSourceTotal }} 张；请注意交叠及中间时段。</p><template #footer><button class="mr-2 rounded-lg border px-4 py-2 dark:border-gray-600" @click="previewMerge">预览范围</button><button class="rounded-lg bg-primary-500 px-4 py-2 text-white disabled:opacity-40" :disabled="!mergePreview" @click="mergeChapter">确认合并</button></template></el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import type { ChapterDetail, ChapterEvent, ChapterItem, ChapterPhoto } from '@/types/chapter'
import type { AlbumImage } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { toServerUrl } from '@/config/server'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const route = useRoute()
const router = useRouter()
const chapter = ref<ChapterDetail | null>(null)
const loading = ref(true)
const page = ref(0)
const yearPhotos = ref<ChapterPhoto[]>([])
const yearEvents = ref<ChapterEvent[]>([])
const yearEventTotal = ref(0)
const yearTotal = ref(0)
const lightboxIndex = ref(-1)
const menuVisible = ref(false)
const splitVisible = ref(false)
const mergeVisible = ref(false)
const splitForm = reactive({ split_date: '', first_title: '', second_title: '' })
const mergeOptions = ref<ChapterItem[]>([])
const mergeTargetId = ref('')
const mergeTitle = ref('')
const mergePreview = ref<{ photo_count: number } | null>(null)
const currentYear = computed(() => chapter.value?.years[page.value - 1] || null)
const mergeTarget = computed(() => mergeOptions.value.find(item => item.id === mergeTargetId.value))
const mergeSourceTotal = computed(() => (chapter.value?.photo_count || 0) + (mergeTarget.value?.photo_count || 0))
const lightboxImages = computed<AlbumImage[]>(() => yearPhotos.value.map(photo => ({ id: photo.id,
  url: toServerUrl(`/api/medias/${photo.id}/file`), thumbnail: thumbnailUrl(photo.id, 'small'),
  preview: thumbnailUrl(photo.id, 'medium'), srcset: '', timestamp: new Date(photo.photo_time).getTime(),
  hasPhotoTime: true, albumIds: [], filename: photo.filename, width: photo.width || undefined,
  height: photo.height || undefined, file_type: photo.file_type as AlbumImage['file_type'] })))

async function load() {
  loading.value = true
  try { chapter.value = await chapterApi.detail(String(route.params.id), route.query.manage === '1'); page.value = 0 }
  catch { ElMessage.error('章节不存在或已隐藏'); router.replace('/chapters') }
  finally { loading.value = false }
}
watch(currentYear, async year => {
  yearPhotos.value = []; yearEvents.value = []; yearTotal.value = 0; yearEventTotal.value = 0
  if (!year || !chapter.value) return
  try { const [result, memories] = await Promise.all([
    chapterApi.photos(chapter.value.id, year, 0, 6, route.query.manage === '1'),
    chapterApi.events(chapter.value.id, 0, 6, year, route.query.manage === '1'),
  ]); if (year === currentYear.value) { yearPhotos.value = result.items; yearTotal.value = result.total; yearEvents.value = memories.items; yearEventTotal.value = memories.total } }
  catch { ElMessage.error('加载这一年的照片失败') }
})
async function loadMore() {
  if (!chapter.value || !currentYear.value) return
  try { const result = await chapterApi.photos(chapter.value.id, currentYear.value, yearPhotos.value.length, 30, route.query.manage === '1'); yearPhotos.value.push(...result.items) }
  catch { ElMessage.error('加载照片失败') }
}
async function loadMoreEvents() {
  if (!chapter.value || !currentYear.value) return
  try { const result = await chapterApi.events(chapter.value.id, yearEvents.value.length, 20, currentYear.value, route.query.manage === '1'); yearEvents.value.push(...result.items) }
  catch { ElMessage.error('加载记忆失败') }
}
async function perform(action: 'confirm' | 'ignore' | 'unhide' | 'hide') {
  if (!chapter.value) return
  if (action === 'hide') {
    try { await ElMessageBox.confirm('隐藏后，章节不会出现在常规入口和推荐中；原照片与记忆仍在各自页面。', '隐藏章节') }
    catch { return }
  }
  try {
    const result = await chapterApi.action(chapter.value.id, action, chapter.value.version)
    menuVisible.value = false
    if (action === 'ignore' || action === 'hide') router.replace('/chapters')
    else { chapter.value = await chapterApi.detail(result.id, action === 'unhide' ? false : route.query.manage === '1'); ElMessage.success('章节已更新') }
  } catch { ElMessage.error('操作失败，请刷新后重试') }
}
async function remove() {
  if (!chapter.value) return
  try { await ElMessageBox.confirm('仅删除章节定义，原照片与记忆仍会保留。', '删除章节') }
  catch { return }
  try { await chapterApi.remove(chapter.value.id, chapter.value.version); router.replace('/chapters') }
  catch { ElMessage.error('删除失败，请刷新后重试') }
}
function openSplit() {
  if (!chapter.value) return
  menuVisible.value = false
  splitForm.split_date = chapter.value.start_date
  splitForm.first_title = `${chapter.value.title} · 前篇`
  splitForm.second_title = `${chapter.value.title} · 后篇`
  splitVisible.value = true
}
async function splitChapter() {
  if (!chapter.value) return
  try { const rows = await chapterApi.split(chapter.value.id, { ...splitForm, version: chapter.value.version }); splitVisible.value = false; await router.replace(`/chapters/${rows[0].id}`); ElMessage.success('章节已拆分') }
  catch { ElMessage.error('拆分失败，请检查日期和名称') }
}
async function openMerge() {
  if (!chapter.value) return
  menuVisible.value = false
  try { const result = await chapterApi.list(chapter.value.status === 'candidate' ? 'candidate' : 'confirmed', chapter.value.is_hidden, 0, 50); mergeOptions.value = result.items.filter(item => item.id !== chapter.value?.id); mergeTitle.value = chapter.value.title; mergeVisible.value = true }
  catch { ElMessage.error('加载可合并章节失败') }
}
watch(mergeTargetId, () => { mergePreview.value = null })
async function previewMerge() {
  if (!chapter.value || !mergeTarget.value) return
  const start = chapter.value.start_date < mergeTarget.value.start_date ? chapter.value.start_date : mergeTarget.value.start_date
  const end = !chapter.value.end_date || !mergeTarget.value.end_date ? null : chapter.value.end_date > mergeTarget.value.end_date ? chapter.value.end_date : mergeTarget.value.end_date
  try { mergePreview.value = await chapterApi.preview(start, end) }
  catch { ElMessage.error('预览合并范围失败') }
}
async function mergeChapter() {
  if (!chapter.value || !mergeTarget.value || !mergePreview.value || !mergeTitle.value.trim()) return
  const start = chapter.value.start_date < mergeTarget.value.start_date ? chapter.value.start_date : mergeTarget.value.start_date
  const end = !chapter.value.end_date || !mergeTarget.value.end_date ? null : chapter.value.end_date > mergeTarget.value.end_date ? chapter.value.end_date : mergeTarget.value.end_date
  try { const result = await chapterApi.merge({ chapter_ids: [chapter.value.id, mergeTarget.value.id],
    versions: { [chapter.value.id]: chapter.value.version, [mergeTarget.value.id]: mergeTarget.value.version },
    title: mergeTitle.value.trim(), summary: chapter.value.summary, start_date: start, end_date: end, cover_photo_id: null }); mergeVisible.value = false; await router.replace(`/chapters/${result.id}`); ElMessage.success('章节已合并') }
  catch { ElMessage.error('合并失败，请刷新后重试') }
}
function keydown(event: KeyboardEvent) {
  if (menuVisible.value || splitVisible.value || mergeVisible.value || !chapter.value || ['INPUT', 'TEXTAREA'].includes((event.target as HTMLElement)?.tagName)) return
  if (event.key === 'ArrowRight') page.value = Math.min(chapter.value.years.length, page.value + 1)
  if (event.key === 'ArrowLeft') page.value = Math.max(0, page.value - 1)
}
onMounted(() => { load(); window.addEventListener('keydown', keydown) })
onUnmounted(() => window.removeEventListener('keydown', keydown))
watch(() => route.params.id, () => { if (route.params.id) load() })
</script>
