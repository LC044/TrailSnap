<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-gray-900 md:px-8">
    <div class="mx-auto max-w-5xl">
      <button class="text-sm text-primary-600 dark:text-primary-400" @click="router.back()">← 返回章节</button>
      <h1 class="mt-5 font-serif text-3xl text-gray-900 dark:text-white">{{ chapter ? '整理这本影像日记' : '把这些年的照片，装订成日记' }}</h1>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">先选一段时光和一张封面。日记会按年份收录照片，每一页都可以手写或让 AI 起草。</p>
      <div class="mt-7 grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <form class="space-y-5 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 md:p-7" @submit.prevent="save(false)">
          <label class="block text-sm text-gray-800 dark:text-gray-200">章节名称
            <input v-model.trim="form.title" maxlength="80" required class="mt-2 w-full rounded-lg border border-gray-300 bg-white p-3 dark:border-gray-600 dark:bg-gray-900" />
          </label>
          <label class="block text-sm text-gray-800 dark:text-gray-200">扉页简介（选填）
            <textarea v-model="form.summary" maxlength="1000" rows="4" class="mt-2 w-full rounded-lg border border-gray-300 bg-white p-3 dark:border-gray-600 dark:bg-gray-900" placeholder="写下这段日子对你的意义" />
          </label>
          <div class="rounded-xl bg-primary-50 p-4 text-sm dark:bg-primary-900/20">
            <p v-if="!chapter" class="text-gray-600 dark:text-gray-300">创建后即可翻阅日记，用 AI 起草扉页简介和年度故事，也可以慢慢手写。</p>
            <template v-else>
              <button type="button" class="min-h-11 text-primary-600 disabled:opacity-50 dark:text-primary-400" :disabled="introBusy || chapter.is_hidden" @click="generateIntroduction">{{ introBusy ? 'AI 正在起草…' : '✧ AI 帮我写扉页简介' }}</button>
              <p v-if="diaryStore.errors[introKey]" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ diaryStore.errors[introKey] }}</p>
              <div v-if="introDraft" class="mt-2 border-t border-primary-200 pt-3 dark:border-primary-800"><p class="text-xs text-gray-500 dark:text-gray-400">AI 草稿 · 尚未保存</p><p class="mt-2 whitespace-pre-wrap leading-7 text-gray-700 dark:text-gray-200">{{ introDraft.body }}</p><button type="button" class="mt-2 min-h-11 text-primary-600 disabled:opacity-50 dark:text-primary-400" :disabled="introDraft.version !== chapter.version || introBusy" @click="acceptIntroduction">采用这段文字</button></div>
            </template>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <label for="chapter-start-date" class="block min-w-0 text-sm text-gray-800 dark:text-gray-200">开始日期<el-date-picker id="chapter-start-date" v-model="form.start_date" type="date" format="YYYY年MM月DD日" value-format="YYYY-MM-DD" placeholder="选择开始日期" :clearable="false" size="large" class="mt-2 !w-full" /></label>
            <label for="chapter-end-date" class="block min-w-0 text-sm text-gray-800 dark:text-gray-200">结束日期<el-date-picker id="chapter-end-date" v-model="form.end_date" :disabled="ongoing" type="date" format="YYYY年MM月DD日" value-format="YYYY-MM-DD" placeholder="选择结束日期" :clearable="false" size="large" class="mt-2 !w-full" /></label>
          </div>
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"><input v-model="ongoing" type="checkbox" />持续中</label>
          <div v-if="previewing" class="text-sm text-gray-500 dark:text-gray-400" role="status">正在更新照片分布…</div>
          <div v-if="preview" class="rounded-xl bg-primary-50 p-4 text-sm text-gray-700 dark:bg-primary-900/20 dark:text-gray-300">
            <p>这段时间有 <strong>{{ preview.photo_count }}</strong> 张影像<span v-if="preview.added_photo_count !== undefined"> · 新增 {{ preview.added_photo_count }} 张 · 移出 {{ preview.removed_photo_count }} 张</span>。原照片不会被修改。</p>
            <div v-if="preview.month_counts.length" class="mt-4 flex h-20 items-end gap-1 overflow-x-auto" aria-label="每月照片数量">
              <div v-for="month in preview.month_counts" :key="month.month" class="group flex h-full min-w-2 flex-1 items-end" :title="`${month.month}：${month.count} 张`">
                <div class="w-full rounded-t bg-primary-500" :style="{ height: `${Math.max(8, month.count / maxMonthCount * 100)}%` }" />
              </div>
            </div>
            <p v-if="preview.month_counts.length" class="mt-1 text-xs">{{ preview.month_counts[0]?.month }} 至 {{ preview.month_counts[preview.month_counts.length - 1]?.month }} · 柱高代表每月照片数</p>
          </div>
          <div v-if="preview?.preview_photo_ids.length">
            <p class="mb-3 text-sm text-gray-700 dark:text-gray-300">选择封面</p>
            <div class="grid grid-cols-4 gap-2 sm:grid-cols-6">
              <button v-for="id in preview.preview_photo_ids" :key="id" type="button" class="aspect-square overflow-hidden rounded-lg border-2 bg-gray-100 dark:bg-gray-700" :class="form.cover_photo_id === id ? 'border-primary-500' : 'border-transparent'" :aria-label="`选择封面 ${id}`" @click="form.cover_photo_id = id">
                <img :src="thumbnailUrl(id, 'small')" alt="章节封面备选照片" class="h-full w-full object-cover" loading="lazy" @error="hideBrokenThumbnail" />
              </button>
            </div>
          </div>
          <button v-if="preview && preview.photo_count" type="button" class="text-sm text-primary-600 dark:text-primary-400" @click="openCoverPicker">浏览全部照片，选择封面 →</button>
          <div class="sticky bottom-20 z-10 flex flex-wrap justify-end gap-2 border-t border-gray-200 bg-white pb-[max(0.75rem,var(--ts-safe-area-bottom))] pt-5 dark:border-gray-700 dark:bg-gray-800 md:bottom-0">
            <button type="button" class="rounded-lg border border-gray-300 px-4 py-2 dark:border-gray-600" @click="router.back()">取消</button>
            <button type="submit" class="min-h-11 rounded-lg px-4 py-2 disabled:opacity-50" :class="chapter?.status === 'candidate' ? 'border border-primary-300 text-primary-600 dark:border-primary-700 dark:text-primary-400' : 'bg-primary-500 text-white'" :disabled="saving || !validRange || !form.title.trim()">{{ saving ? '保存中' : chapter?.status === 'candidate' ? '保存建议' : chapter ? '保存日记' : '创建并翻开日记' }}</button>
            <button v-if="chapter?.status === 'candidate'" type="button" class="rounded-lg bg-primary-500 px-5 py-2 text-white disabled:opacity-50" :disabled="saving || !validRange || !form.title.trim()" @click="save(true)">确认并保存</button>
          </div>
        </form>
        <aside class="h-fit rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <h2 class="mb-3 text-sm font-semibold text-gray-900 dark:text-white">目录封面预览</h2>
          <div class="relative aspect-[3/2] overflow-hidden rounded-xl bg-gray-200 dark:bg-gray-700">
            <img v-if="form.cover_photo_id" :src="thumbnailUrl(form.cover_photo_id, 'medium')" alt="目录封面预览" class="h-full w-full object-cover" />
            <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-5 pt-20 text-white"><p class="text-xs">{{ form.start_date }} — {{ ongoing ? '至今' : form.end_date }}</p><h2 class="mt-2 font-serif text-2xl">{{ form.title || '未命名章节' }}</h2></div>
          </div>
          <p class="mt-4 text-xs leading-6 text-gray-500 dark:text-gray-400">未选择封面时，系统会从这一阶段的有效照片中选取。照片仅按时间归属，不会据此推断你的身份或经历。</p>
        </aside>
      </div>
      <el-dialog v-model="coverPickerVisible" title="选择章节封面" width="min(94vw, 760px)">
        <p class="mb-3 text-sm text-gray-500 dark:text-gray-400">按拍摄时间从近到远浏览；选择后可在右侧查看目录效果。</p>
        <div v-if="coverLoading" class="py-8 text-center text-sm text-gray-500 dark:text-gray-400">正在加载照片…</div>
        <div class="grid max-h-[60vh] grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-5">
          <button v-for="photo in coverOptions" :key="photo.id" type="button" class="aspect-square overflow-hidden rounded-lg border-2 bg-gray-100 dark:bg-gray-700" :class="form.cover_photo_id === photo.id ? 'border-primary-500' : 'border-transparent'" :aria-label="`选择 ${photo.photo_time.slice(0, 10)} 的照片作为封面`" @click="form.cover_photo_id = photo.id; coverPickerVisible = false">
            <img :src="thumbnailUrl(photo.id, 'small')" :alt="photo.photo_time.slice(0, 10)" class="h-full w-full object-cover" loading="lazy" @error="hideBrokenThumbnail" />
          </button>
        </div>
        <button v-if="coverOptions.length < coverTotal" type="button" class="mt-4 rounded-lg border border-primary-200 px-4 py-2 text-sm text-primary-600 disabled:opacity-50 dark:border-primary-800 dark:text-primary-400" :disabled="coverLoading" @click="loadCoverOptions">加载更多（{{ coverOptions.length }} / {{ coverTotal }}）</button>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import { useChapterDiaryStore } from '@/stores/chapterDiaryStore'
import type { ChapterDetail } from '@/types/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'

const route = useRoute()
const router = useRouter()
const chapter = ref<ChapterDetail | null>(null)
const diaryStore = useChapterDiaryStore()
const introKey = computed(() => diaryStore.key(chapter.value?.id || '', null))
const introDraft = computed(() => diaryStore.drafts[introKey.value])
const introBusy = computed(() => diaryStore.generating[introKey.value])
const summarySource = ref<'user' | 'ai'>('user')
async function generateIntroduction() {
  if (!chapter.value) return
  if (form.title !== chapter.value.title || form.start_date !== chapter.value.start_date || (ongoing.value ? null : form.end_date) !== chapter.value.end_date) {
    ElMessage.info('请先保存名称和时间，再根据新的照片范围起草')
    return
  }
  await diaryStore.generate(chapter.value.id, null, chapter.value.version, form.summary)
}
function acceptIntroduction() {
  if (!introDraft.value || introDraft.value.version !== chapter.value?.version) return
  form.summary = introDraft.value.body
  summarySource.value = 'ai'
}
const saving = ref(false)
const previewing = ref(false)
const preview = ref<Awaited<ReturnType<typeof chapterApi.preview>> | null>(null)
const maxMonthCount = computed(() => Math.max(1, ...(preview.value?.month_counts.map(item => item.count) || [])))
const coverPickerVisible = ref(false)
const coverLoading = ref(false)
const coverOptions = ref<Array<{ id: string; photo_time: string }>>([])
const coverTotal = ref(0)
const ongoing = ref(false)
const form = reactive({ title: '', summary: '', start_date: '', end_date: '', cover_photo_id: '' })
let originalForm = ''
function formSnapshot() { return JSON.stringify([form, ongoing.value]) }
onBeforeRouteLeave(async () => {
  if (!originalForm || originalForm === formSnapshot()) return true
  try { await ElMessageBox.confirm('日记的修改还没有保存，离开后会丢失。', '离开编辑', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' }); return true }
  catch { return false }
})
function hideBrokenThumbnail(event: Event) {
  const image = event.target as HTMLImageElement
  image.style.display = 'none'
  const button = image.closest('button')
  if (button) { button.disabled = true; button.title = '缩略图不可用' }
}
const validRange = computed(() => Boolean(form.start_date && (ongoing.value || (form.end_date && form.end_date >= form.start_date))))
let previewTimer: ReturnType<typeof setTimeout> | null = null
let previewRequest = 0
watch(() => [form.start_date, form.end_date, ongoing.value], () => {
  previewRequest++
  preview.value = null
  coverOptions.value = []
  if (previewTimer) clearTimeout(previewTimer)
  if (validRange.value) previewTimer = setTimeout(() => { void loadPreview() }, 350)
})

async function loadPreview() {
  if (!validRange.value) return
  const requestId = ++previewRequest
  previewing.value = true
  try { const result = await chapterApi.preview(form.start_date, ongoing.value ? null : form.end_date || null, chapter.value?.id); if (requestId === previewRequest) preview.value = result }
  catch { if (requestId === previewRequest) ElMessage.error('预览范围失败') }
  finally { if (requestId === previewRequest) previewing.value = false }
}
async function openCoverPicker() {
  coverPickerVisible.value = true
  coverOptions.value = []
  await loadCoverOptions()
}
async function loadCoverOptions() {
  if (coverLoading.value || !validRange.value) return
  coverLoading.value = true
  try {
    const result = await chapterApi.coverOptions(form.start_date, ongoing.value ? null : form.end_date || null, coverOptions.value.length)
    coverOptions.value.push(...result.items)
    coverTotal.value = result.total
  } catch { ElMessage.error('加载封面照片失败') }
  finally { coverLoading.value = false }
}

async function save(confirmAfter: boolean) {
  if (!validRange.value || !form.title.trim()) return
  saving.value = true
  try {
    const payload = { title: form.title.trim(), summary: form.summary, summary_source: summarySource.value, start_date: form.start_date,
      end_date: ongoing.value ? null : form.end_date || null, cover_photo_id: form.cover_photo_id || null }
    const result = chapter.value
      ? await chapterApi.update(chapter.value.id, { ...payload, version: chapter.value.version })
      : await chapterApi.create(payload)
    originalForm = formSnapshot()
    delete diaryStore.drafts[introKey.value]
    if (confirmAfter && chapter.value?.status === 'candidate') {
      try { await chapterApi.action(result.id, 'confirm', result.version) }
      catch { ElMessage.warning('修改已保存，确认未完成，请在建议详情重试'); await router.replace(`/chapters/${result.id}`); return }
    }
    ElMessage.success(confirmAfter ? '章节已确认' : chapter.value?.status === 'candidate' ? '建议已保存，仍待确认' : '章节已保存')
    router.replace(`/chapters/${result.id}${chapter.value?.is_hidden ? '?manage=1' : ''}`)
  } catch { ElMessage.error('保存失败，请检查封面是否仍在章节时间范围内') }
  finally { saving.value = false }
}

onMounted(async () => {
  if (route.params.id) {
    try {
      chapter.value = await chapterApi.detail(String(route.params.id), true)
      form.title = chapter.value.title
      form.summary = chapter.value.summary || ''
      summarySource.value = chapter.value.summary_source || 'user'
      form.start_date = chapter.value.start_date
      form.end_date = chapter.value.end_date || ''
      form.cover_photo_id = chapter.value.cover_photo_id || ''
      ongoing.value = !chapter.value.end_date
      await loadPreview()
    } catch { ElMessage.error('加载章节失败'); router.replace('/chapters') }
  }
  originalForm = formSnapshot()
})
onUnmounted(() => { if (previewTimer) clearTimeout(previewTimer); previewRequest++ })
</script>
