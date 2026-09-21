<template>
  <div class="min-h-full bg-gray-50 dark:bg-gray-900">
    <div v-if="loading" class="flex min-h-[70vh] items-center justify-center"><LoaderCircle class="h-8 w-8 animate-spin text-primary-500" /></div>
    <template v-else-if="memory">
      <div class="relative h-[34vh] min-h-[280px] max-h-[480px] overflow-hidden bg-gray-900">
        <img v-if="memory.cover_photo_id" :src="thumbnailUrl(memory.cover_photo_id, 'medium')" :alt="memory.title" class="h-full w-full object-cover" />
        <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/15 to-black/30"></div>
        <div class="absolute left-0 right-0 top-0 flex items-center justify-between p-4 md:p-6">
          <button class="rounded-full bg-black/25 p-2 text-white backdrop-blur hover:bg-black/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" aria-label="返回" @click="router.back()"><ArrowLeft class="h-5 w-5" /></button>
          <button class="rounded-lg bg-white/95 px-4 py-2 text-sm font-medium text-gray-800 shadow hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" @click="openEdit"><Pencil class="mr-1.5 inline h-4 w-4" />编辑记忆</button>
        </div>
        <div class="absolute bottom-0 left-0 right-0 mx-auto max-w-6xl px-5 pb-7 text-white md:px-8">
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <span v-if="memory.status === 'candidate'" class="rounded-full bg-amber-400/95 px-3 py-1 text-xs font-semibold text-amber-950">待确认</span>
            <span v-else class="rounded-full bg-emerald-500/90 px-3 py-1 text-xs font-semibold text-white">已确认</span>
            <span v-if="memory.status === 'candidate'" class="rounded-full bg-white/20 px-3 py-1 text-xs backdrop-blur">{{ memory.confidence_level === 'strong' ? '依据充分' : '需要检查' }}</span>
          </div>
          <h1 class="text-3xl font-bold tracking-tight md:text-5xl">{{ memory.title }}</h1>
          <div class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-white/90">
            <span class="inline-flex items-center gap-1.5"><CalendarDays class="h-4 w-4" />{{ formatRange(memory.start_time, memory.end_time) }}</span>
            <span v-if="memory.places.length" class="inline-flex items-center gap-1.5"><MapPin class="h-4 w-4" />{{ memory.places.map(item => item.name).join(' · ') }}</span>
            <span class="inline-flex items-center gap-1.5"><Images class="h-4 w-4" />{{ memory.photo_count }} 张照片</span>
          </div>
        </div>
      </div>

      <main class="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:px-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div class="space-y-6">
          <section v-if="memory.status === 'candidate'" class="rounded-2xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-800/60 dark:bg-amber-950/30">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 class="font-semibold text-gray-900 dark:text-white">这是一段候选记忆</h2>
                <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">确认前所有信息都只是建议，你可以先调整照片、标题和地点。</p>
              </div>
              <div class="flex gap-2">
                <button class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="confirmMemory">确认记忆</button>
                <button class="rounded-lg border border-amber-300 px-4 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/40" @click="ignoreMemory">忽略</button>
              </div>
            </div>
          </section>

          <section class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 md:p-6">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h2 class="text-lg font-bold text-gray-900 dark:text-white">这段记忆</h2>
              <button
                v-if="memory.status === 'confirmed'"
                class="rounded-lg bg-primary-50 px-3 py-1.5 text-sm font-medium text-primary-700 hover:bg-primary-100 disabled:opacity-60 dark:bg-primary-900/30 dark:text-primary-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                :disabled="isStoryGenerating"
                @click="generateStory"
              ><Sparkles class="mr-1 inline h-4 w-4" :class="{ 'animate-pulse': isStoryGenerating }" />{{ isStoryGenerating ? '正在创作，请稍候' : memory.story ? 'AI 重新创作' : 'AI 生成故事' }}</button>
            </div>
            <p v-if="memory.story" class="mt-3 whitespace-pre-wrap leading-7 text-gray-700 dark:text-gray-300">{{ memory.story }}</p>
            <button v-else class="mt-3 rounded-lg text-sm text-primary-600 hover:underline dark:text-primary-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" @click="openEdit">写下这段经历</button>
          </section>

          <section class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 md:p-6">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-lg font-bold text-gray-900 dark:text-white">照片时间线</h2>
              <div class="flex items-center gap-2">
                <button class="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" @click="toggleSelectionMode">{{ selectionMode ? '完成选择' : '选择照片' }}</button>
                <button v-if="(memory.photos?.length || 0) > 1" class="rounded-lg px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" @click="openSplit"><Split class="mr-1 inline h-4 w-4" />拆分</button>
              </div>
            </div>
            <div class="mt-6 space-y-8">
              <div v-for="group in photoGroups" :key="group.day" class="relative border-l-2 border-primary-200 pl-5 dark:border-primary-900">
                <span class="absolute -left-[7px] top-1 h-3 w-3 rounded-full bg-primary-500 ring-4 ring-white dark:ring-gray-800"></span>
                <div class="mb-3 flex items-center justify-between">
                  <h3 class="font-semibold text-gray-800 dark:text-gray-100">{{ group.label }}</h3>
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ group.photos.length }} 张</span>
                </div>
                <div class="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5">
                  <button
                    v-for="photo in group.photos"
                    :key="photo.id"
                    class="group/photo relative aspect-square overflow-hidden rounded-lg bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-900"
                    :aria-label="photo.filename"
                    @click="selectionMode ? togglePhoto(photo.id) : openPhoto(photo.id)"
                  >
                    <img :src="thumbnailUrl(photo.id, 'small')" :alt="photo.filename" class="h-full w-full object-cover transition group-hover/photo:scale-105" loading="lazy" />
                    <span v-if="selectionMode && selectedPhotoIds.includes(photo.id)" class="absolute inset-0 flex items-center justify-center bg-primary-500/45"><CheckCircle2 class="h-7 w-7 text-white" /></span>
                  </button>
                </div>
              </div>
            </div>
            <div v-if="selectedPhotoIds.length" class="sticky bottom-4 mt-4 flex items-center justify-between rounded-xl bg-gray-900 px-4 py-3 text-white shadow-xl dark:bg-gray-700">
              <span class="text-sm">已选择 {{ selectedPhotoIds.length }} 张</span>
              <button class="rounded-lg bg-red-500 px-3 py-1.5 text-sm hover:bg-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400" @click="removeSelectedPhotos">从记忆移除</button>
            </div>
          </section>

          <section v-if="memory.tickets?.length" class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 md:p-6">
            <h2 class="text-lg font-bold text-gray-900 dark:text-white">行程票据</h2>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <div v-for="ticket in memory.tickets" :key="`${ticket.type}-${ticket.id}`" class="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
                <div class="flex items-center justify-between"><span class="text-sm font-semibold text-primary-600 dark:text-primary-400">{{ ticket.type === 'train' ? '火车票' : '机票' }}</span><span class="font-mono text-sm text-gray-700 dark:text-gray-200">{{ ticket.code }}</span></div>
                <div class="mt-3 flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200"><span>{{ ticket.from }}</span><ArrowRight class="h-4 w-4 text-gray-400" /><span>{{ ticket.to }}</span></div>
                <p v-if="ticket.date_time" class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ formatDateTime(ticket.date_time) }}</p>
              </div>
            </div>
          </section>
        </div>

        <aside class="space-y-5">
          <section v-if="memory.evidence.length" class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
            <h2 class="flex items-center gap-2 font-bold text-gray-900 dark:text-white"><Sparkles class="h-4 w-4 text-primary-500" />形成依据</h2>
            <ul class="mt-4 space-y-3">
              <li v-for="item in memory.evidence" :key="item.id" class="flex gap-3 text-sm text-gray-600 dark:text-gray-300">
                <span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-amber-400"></span><span>{{ item.summary }}</span>
              </li>
            </ul>
            <p class="mt-4 text-xs text-gray-400 dark:text-gray-500">待确认依据不会自动成为用户事实。</p>
          </section>
          <section v-if="memory.people.length" class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
            <h2 class="font-bold text-gray-900 dark:text-white">人物</h2>
            <div class="mt-4 space-y-3">
              <div v-for="person in memory.people" :key="person.id" class="flex items-center gap-3">
                <span class="flex h-9 w-9 items-center justify-center rounded-full bg-primary-100 font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">{{ person.name.slice(0, 1) }}</span>
                <span class="text-sm text-gray-700 dark:text-gray-200">{{ person.name }}</span>
                <span v-if="!person.confirmed" class="ml-auto text-xs text-amber-600 dark:text-amber-400">待确认</span>
              </div>
            </div>
          </section>
          <button v-if="memory.status === 'confirmed'" class="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 hover:border-red-200 hover:text-red-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300" @click="deleteMemory">删除这段记忆</button>
        </aside>
      </main>
    </template>

    <PhotoLightbox
      v-if="lightboxIndex >= 0"
      :visible="true"
      :image="lightboxImages[lightboxIndex] || null"
      :images="lightboxImages"
      :current-index="lightboxIndex"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex < lightboxImages.length - 1"
      @close="lightboxIndex = -1"
      @prev="lightboxIndex = Math.max(0, lightboxIndex - 1)"
      @next="lightboxIndex = Math.min(lightboxImages.length - 1, lightboxIndex + 1)"
      @select="lightboxIndex = $event"
    />

    <el-dialog v-model="editVisible" title="编辑记忆" width="min(94vw, 620px)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="255" show-word-limit /></el-form-item>
        <el-form-item label="故事"><el-input v-model="form.story" type="textarea" :rows="5" maxlength="50000" /></el-form-item>
        <div class="grid gap-3 sm:grid-cols-2">
          <el-form-item label="开始时间"><el-date-picker v-model="form.start_time" type="datetime" class="!w-full" /></el-form-item>
          <el-form-item label="结束时间"><el-date-picker v-model="form.end_time" type="datetime" class="!w-full" /></el-form-item>
        </div>
        <el-form-item label="地点（用顿号分隔）"><el-input v-model="form.places" placeholder="杭州、西湖" /></el-form-item>
        <el-form-item label="封面">
          <el-select v-model="form.cover_photo_id" class="w-full">
            <el-option v-for="photo in memory?.photos || []" :key="photo.id" :label="photo.filename" :value="photo.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="splitVisible" title="拆分记忆" width="min(94vw, 620px)">
      <p class="text-sm text-gray-500 dark:text-gray-400">选择第二段记忆开始的位置。所有照片会按拍摄时间完整分配。</p>
      <div v-if="memory?.photos?.length" class="mt-6">
        <el-slider v-model="splitIndex" :min="1" :max="memory.photos.length - 1" :show-tooltip="false" />
        <div class="mt-2 grid grid-cols-2 gap-4 text-sm">
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><strong>{{ splitIndex }} 张</strong><el-input v-model="splitTitles[0]" class="mt-2" /></div>
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><strong>{{ memory.photos.length - splitIndex }} 张</strong><el-input v-model="splitTitles[1]" class="mt-2" /></div>
        </div>
      </div>
      <template #footer><el-button @click="splitVisible = false">取消</el-button><el-button type="primary" :loading="splitting" @click="submitSplit">确认拆分</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, CalendarDays, CheckCircle2, Images, LoaderCircle, MapPin, Pencil, Sparkles, Split } from 'lucide-vue-next'
import { memoryApi } from '@/api/memory'
import type { MemoryItem, MemoryPhoto } from '@/types/memory'
import type { AlbumImage } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { toServerUrl } from '@/config/server'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const route = useRoute()
const router = useRouter()
const memory = ref<MemoryItem | null>(null)
const loading = ref(true)
const editVisible = ref(false)
const saving = ref(false)
const selectedPhotoIds = ref<string[]>([])
const selectionMode = ref(false)
const lightboxIndex = ref(-1)
const generatingStory = ref(false)
let storyPollTimer: ReturnType<typeof setTimeout> | null = null
let disposed = false
const splitVisible = ref(false)
const splitIndex = ref(1)
const splitTitles = ref(['第一段记忆', '第二段记忆'])
const splitting = ref(false)
const form = reactive({ title: '', story: '', start_time: null as Date | null, end_time: null as Date | null, places: '', cover_photo_id: '' })

const photoGroups = computed(() => {
  const groups = new Map<string, MemoryPhoto[]>()
  for (const photo of memory.value?.photos || []) {
    const day = photo.photo_time ? photo.photo_time.slice(0, 10) : 'unknown'
    groups.set(day, [...(groups.get(day) || []), photo])
  }
  return Array.from(groups.entries()).map(([day, photos]) => ({
    day, photos,
    label: day === 'unknown' ? '时间待确认' : new Date(`${day}T00:00:00`).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }),
  }))
})
const lightboxImages = computed<AlbumImage[]>(() => (memory.value?.photos || []).map(photo => ({
  id: photo.id,
  url: toServerUrl(`/api/medias/${photo.id}/file`),
  thumbnail: thumbnailUrl(photo.id, 'small'),
  preview: thumbnailUrl(photo.id, 'medium'),
  srcset: '',
  timestamp: photo.photo_time ? new Date(photo.photo_time).getTime() : Date.now(),
  hasPhotoTime: Boolean(photo.photo_time),
  albumIds: [],
  width: photo.width || undefined,
  height: photo.height || undefined,
  filename: photo.filename,
  file_type: (photo.file_type || 'image') as AlbumImage['file_type'],
})))
const isStoryGenerating = computed(() => generatingStory.value || memory.value?.story_generation_status === 'generating')

function formatRange(start: string | null, end: string | null) {
  if (!start) return '时间待确认'
  const first = new Date(start).toLocaleDateString('zh-CN')
  const last = end ? new Date(end).toLocaleDateString('zh-CN') : first
  return first === last ? first : `${first} — ${last}`
}
function formatDateTime(value: string) { return new Date(value).toLocaleString('zh-CN') }
async function load() {
  loading.value = true
  try {
    memory.value = await memoryApi.detail(String(route.params.id))
    scheduleStoryPoll()
  }
  catch { ElMessage.error('加载记忆失败'); router.replace('/memories') }
  finally { loading.value = false }
}
function scheduleStoryPoll() {
  if (storyPollTimer) clearTimeout(storyPollTimer)
  storyPollTimer = null
  if (disposed || memory.value?.story_generation_status !== 'generating') return
  storyPollTimer = setTimeout(async () => {
    try {
      const latest = await memoryApi.detail(String(route.params.id))
      const wasGenerating = memory.value?.story_generation_status === 'generating'
      memory.value = latest
      if (wasGenerating && latest.story_generation_status === 'idle') ElMessage.success('记忆故事已生成')
      if (wasGenerating && latest.story_generation_status === 'failed') ElMessage.error(latest.story_generation_error || '故事生成失败')
    } catch {
      // A transient refresh failure should not unlock the generate button.
    } finally {
      scheduleStoryPoll()
    }
  }, 2500)
}
function openEdit() {
  if (!memory.value) return
  form.title = memory.value.title
  form.story = memory.value.story || ''
  form.start_time = memory.value.start_time ? new Date(memory.value.start_time) : null
  form.end_time = memory.value.end_time ? new Date(memory.value.end_time) : null
  form.places = memory.value.places.map(item => item.name).join('、')
  form.cover_photo_id = memory.value.cover_photo_id || ''
  editVisible.value = true
}
async function saveEdit() {
  if (!memory.value || !form.title.trim()) return
  saving.value = true
  try {
    memory.value = await memoryApi.update(memory.value.id, {
      title: form.title.trim(), story: form.story,
      start_time: form.start_time?.toISOString(), end_time: form.end_time?.toISOString(),
      place_names: form.places.split(/[、,，]/).map(item => item.trim()).filter(Boolean),
      cover_photo_id: form.cover_photo_id || undefined,
    })
    editVisible.value = false
    ElMessage.success('记忆已更新')
  } finally { saving.value = false }
}
async function confirmMemory() { if (memory.value) { memory.value = await memoryApi.confirm(memory.value.id); ElMessage.success('已保存为我的记忆') } }
async function ignoreMemory() { if (memory.value) { await memoryApi.ignore(memory.value.id); ElMessage.success('已忽略'); router.replace('/memories') } }
function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) selectedPhotoIds.value = []
}
function openPhoto(id: string) { lightboxIndex.value = lightboxImages.value.findIndex(photo => photo.id === id) }
function togglePhoto(id: string) { selectedPhotoIds.value = selectedPhotoIds.value.includes(id) ? selectedPhotoIds.value.filter(item => item !== id) : [...selectedPhotoIds.value, id] }
async function removeSelectedPhotos() {
  if (!memory.value) return
  await ElMessageBox.confirm(`从这段记忆移除 ${selectedPhotoIds.value.length} 张照片？原始照片不会被删除。`, '移除照片', { type: 'warning' })
  memory.value = await memoryApi.removePhotos(memory.value.id, selectedPhotoIds.value)
  selectedPhotoIds.value = []
  selectionMode.value = false
  ElMessage.success('照片已从记忆移除')
}
async function generateStory() {
  if (!memory.value || isStoryGenerating.value) return
  if (memory.value.story) {
    try { await ElMessageBox.confirm('AI 生成的新故事会替换当前故事，是否继续？', '重新创作', { type: 'warning' }) }
    catch { return }
  }
  generatingStory.value = true
  try {
    memory.value = await memoryApi.generateStory(memory.value.id)
    ElMessage.success('记忆故事已生成')
  } catch { ElMessage.error('故事生成失败，请检查 AI 模型配置后重试') }
  finally { generatingStory.value = false }
}
function openSplit() {
  if (!memory.value?.photos || memory.value.photos.length < 2) return
  splitIndex.value = Math.max(1, Math.floor(memory.value.photos.length / 2))
  splitTitles.value = [`${memory.value.title}（上）`, `${memory.value.title}（下）`]
  splitVisible.value = true
}
async function submitSplit() {
  if (!memory.value?.photos || splitTitles.value.some(title => !title.trim())) return
  splitting.value = true
  try {
    const parts = [
      { title: splitTitles.value[0], photo_ids: memory.value.photos.slice(0, splitIndex.value).map(item => item.id) },
      { title: splitTitles.value[1], photo_ids: memory.value.photos.slice(splitIndex.value).map(item => item.id) },
    ]
    const result = await memoryApi.split(memory.value.id, parts)
    ElMessage.success('记忆已拆分')
    router.replace(`/memories/${result[0].id}`)
    splitVisible.value = false
    await load()
  } finally { splitting.value = false }
}
async function deleteMemory() {
  if (!memory.value) return
  await ElMessageBox.confirm('只会删除记忆及故事，原始照片和票据不会被删除。', '删除记忆', { type: 'warning', confirmButtonText: '删除' })
  await memoryApi.remove(memory.value.id)
  ElMessage.success('记忆已删除')
  router.replace('/memories')
}

onMounted(load)
onUnmounted(() => { disposed = true; if (storyPollTimer) clearTimeout(storyPollTimer) })
</script>
