<template>
  <div class="memory-spread-page">
    <header class="memory-spread-controls">
      <BackButton label="返回" @click="goBack" />
      <div v-if="memory" class="memory-spread-tools">
        <RouterLink v-if="memory.status === 'confirmed'" :to="{ path: '/explore/relations', query: { root: `memory:${memory.id}` } }" class="memory-tool memory-tool--wide"><Network />关联探索</RouterLink>
        <button type="button" class="memory-tool" aria-label="编辑记忆" @click="openEdit"><Pencil /><span>编辑记忆</span></button>
        <button type="button" class="memory-tool" aria-label="更多记忆操作" :aria-expanded="showActions" @click="showActions = true"><MoreHorizontal /></button>
        <ResponsiveDialog v-model="showActions" title="记忆操作">
          <button v-if="memory.status === 'confirmed'" type="button" class="ts-action-row" @click="showActions = false; router.push({ path: '/explore/relations', query: { root: `memory:${memory.id}` } })"><Network />关联探索</button>
          <button v-if="memory.status === 'confirmed'" type="button" class="ts-action-row" :disabled="isStoryGenerating" @click="showActions = false; generateStory()"><Sparkles />{{ isStoryGenerating ? '正在创作…' : memory.story ? 'AI 重新创作' : 'AI 生成故事' }}</button>
          <button v-if="photoGroups.length" type="button" class="ts-action-row" @click="showActions = false; toggleSelectionMode(); jumpToTimeline()"><ListChecks />{{ selectionMode ? '完成选择' : '选择照片' }}</button>
          <button v-if="(memory.photos?.length || 0) > 1" type="button" class="ts-action-row" @click="showActions = false; openSplit()"><Split />拆分记忆</button>
          <button v-if="memory.status === 'confirmed'" type="button" class="ts-action-row danger" @click="showActions = false; deleteMemory()"><Trash2 />删除这段记忆</button>
        </ResponsiveDialog>
      </div>
    </header>
    <div v-if="loading && !memory" class="memory-spread-skeleton" role="status" aria-label="正在加载记忆"></div>
    <div v-else-if="!memory" class="memory-spread-error" role="status">
      <h1>记忆暂时无法打开</h1>
      <button type="button" class="ts-button ts-button-secondary" @click="load">重试</button>
    </div>
    <template v-else>
      <section class="memory-spread-cover" aria-labelledby="memory-title">
        <div class="memory-spread-heading">
          <p class="memory-spread-date"><CalendarDays aria-hidden="true" />{{ formatRange(memory.start_time, memory.end_time) }}</p>
          <h1 id="memory-title">{{ memory.title }}</h1>
          <div v-if="memory.places.length" class="memory-spread-places">
            <MapPin aria-hidden="true" />
            <ul><li v-for="place in memory.places" :key="place.id">{{ place.name }}</li></ul>
          </div>
          <div class="memory-spread-heading-actions">
            <button v-if="photoGroups.length" type="button" class="memory-tool memory-tool--primary" @click="jumpToTimeline"><Images />浏览 {{ memory.photo_count }} 张照片 <ArrowDown /></button>
          </div>
        </div>
        <div class="memory-spread-image">
          <img v-if="coverPhotoId && coverPhotoId !== failedCover" :src="thumbnailUrl(coverPhotoId, 'medium')" alt="" fetchpriority="high" @error="failedCover = coverPhotoId" />
          <Images v-else class="memory-spread-placeholder" aria-hidden="true" />
        </div>
      </section>

      <section v-if="memory.status === 'candidate'" class="memory-spread-review" aria-label="候选记忆">
        <span><strong>待确认</strong>{{ memory.confidence_level === 'strong' ? '已有线索支持这段记忆' : '确认前可以先调整照片、标题和地点' }}</span>
        <div class="flex shrink-0 gap-2">
          <button type="button" class="memory-tool" @click="ignoreMemory">忽略</button>
          <button type="button" class="memory-tool memory-tool--primary" @click="confirmMemory"><Check />确认记忆</button>
        </div>
      </section>

      <div class="memory-spread-content">
        <div class="memory-spread-primary">
          <section class="memory-story">
            <div class="memory-spread-section-heading">
              <h2>这段记忆</h2>
              <button v-if="memory.status === 'confirmed'" type="button" class="memory-tool" :disabled="isStoryGenerating" @click="generateStory"><Sparkles />{{ isStoryGenerating ? '正在创作…' : memory.story ? 'AI 重新创作' : 'AI 生成故事' }}</button>
            </div>
            <p v-if="memory.story" class="memory-story-text">{{ memory.story }}</p>
            <button v-else type="button" class="memory-story-write" @click="openEdit"><Pencil />写下这段经历</button>
          </section>

          <section ref="photoTimeline" tabindex="-1" class="memory-photo-timeline" aria-labelledby="memory-timeline-title">
            <div class="memory-spread-section-heading">
              <h2 id="memory-timeline-title">照片时间线</h2>
              <button v-if="photoGroups.length" type="button" class="memory-tool" :aria-pressed="selectionMode" @click="toggleSelectionMode"><ListChecks />{{ selectionMode ? '完成选择' : '选择照片' }}</button>
            </div>
            <nav v-if="photoGroups.length > 1" class="memory-day-nav" aria-label="跳到拍摄日期">
              <button v-for="group in photoGroups" :key="group.day" :aria-label="`跳到 ${group.label}`" type="button" @click="jumpToDay(group.day)">{{ group.day === 'unknown' ? '时间待确认' : group.day }}</button>
            </nav>
            <div v-if="!photoGroups.length" class="memory-story-write">这段记忆还没有照片</div>
            <section v-for="group in photoGroups" :id="`memory-day-${group.day}`" :key="group.day" tabindex="-1" class="memory-day">
              <div class="memory-day-heading"><h3>{{ group.label }}</h3><span>{{ group.photos.length }} 张</span></div>
              <div class="memory-photo-grid" :class="{ 'memory-photo-grid--single': group.photos.length === 1 }">
                <button
                  v-for="photo in group.photos"
                  :key="photo.id"
                  type="button"
                  class="memory-photo"
                  :aria-label="photo.filename || '查看照片'"
                  :aria-pressed="selectionMode ? selectedPhotoIds.includes(photo.id) : undefined"
                  @click="selectionMode ? togglePhoto(photo.id) : openPhoto(photo.id)"
                >
                  <img :src="thumbnailUrl(photo.id, group.photos.length === 1 ? 'medium' : 'small')" alt="" loading="lazy" />
                  <Play v-if="photo.file_type === 'video'" class="memory-photo-play" aria-hidden="true" />
                  <span v-if="selectionMode" class="memory-photo-selected"><CheckCircle2 v-if="selectedPhotoIds.includes(photo.id)" aria-hidden="true" /><Circle v-else aria-hidden="true" /></span>
                </button>
              </div>
            </section>
            <div v-if="selectedPhotoIds.length" class="memory-selected-dock">
              <span class="text-sm" aria-live="polite">已选择 {{ selectedPhotoIds.length }} 张</span>
              <button type="button" class="ts-button ts-button-danger" @click="removeSelectedPhotos">从记忆移除</button>
            </div>
          </section>

          <TicketContextSection v-if="memory.status === 'confirmed'" kind="memory" :context-id="memory.id" editable @changed="load" />
        </div>

        <aside v-if="memory.evidence.length || memory.people.length || memory.places.length" class="memory-spread-notes" aria-label="记忆线索">
          <section v-if="memory.places.length">
            <h2><MapPin />地点</h2>
            <ul><li v-for="place in memory.places" :key="place.id">{{ place.name }}</li></ul>
          </section>
          <section v-if="memory.people.length">
            <h2><Users />人物</h2>
            <ul><li v-for="person in memory.people" :key="person.id">{{ person.name }}<small v-if="!person.confirmed">待确认</small></li></ul>
          </section>
          <section v-if="memory.evidence.length">
            <h2><Sparkles />形成依据</h2>
            <ul><li v-for="item in memory.evidence" :key="item.id">{{ item.summary }}</li></ul>
          </section>
        </aside>
      </div>
    </template>

    <PhotoLightbox
      v-if="lightboxIndex >= 0"
      :visible="true"
      :image="lightboxImages[lightboxIndex] || null"
      :images="lightboxImages"
      :current-index="lightboxIndex"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex < lightboxImages.length - 1"
      @close="closePhoto"
      @prev="lightboxIndex = Math.max(0, lightboxIndex - 1)"
      @next="lightboxIndex = Math.min(lightboxImages.length - 1, lightboxIndex + 1)"
      @select="lightboxIndex = $event"
    />

    <el-dialog v-model="editVisible" title="编辑记忆" width="min(94vw, 620px)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="255" show-word-limit /></el-form-item>
        <el-form-item label="故事"><el-input v-model="form.story" type="textarea" :rows="5" maxlength="50000" /></el-form-item>
        <div class="grid gap-3 sm:grid-cols-2">
          <el-form-item label="开始时间"><UnifiedDatePicker v-model="form.start_time" type="datetime" class="!w-full" /></el-form-item>
          <el-form-item label="结束时间"><UnifiedDatePicker v-model="form.end_time" type="datetime" class="!w-full" /></el-form-item>
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
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import TicketContextSection from '@/views/ticket/components/TicketContextSection.vue'
import BackButton from '@/components/ui/BackButton.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, CalendarDays, Check, CheckCircle2, Circle, Images, ListChecks, MapPin, MoreHorizontal, Network, Pencil, Play, Sparkles, Split, Trash2, Users } from 'lucide-vue-next'
import { memoryApi } from '@/api/memory'
import type { MemoryItem, MemoryPhoto } from '@/types/memory'
import type { AlbumImage } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { toServerUrl } from '@/config/server'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const route = useRoute()
const showActions = ref(false)
const router = useRouter()
const goBack = useAppBack('/memories')
const memory = ref<MemoryItem | null>(null)
const coverPhotoId = computed(() => memory.value?.cover_photo_id || memory.value?.photos?.[0]?.id || '')
const failedCover = ref('')
const photoTimeline = ref<HTMLElement | null>(null)
const loading = ref(true)
const editVisible = ref(false)
const saving = ref(false)
const selectedPhotoIds = ref<string[]>([])
const selectionMode = ref(false)
const lightboxIndex = ref(-1)
let photoTrigger: HTMLElement | null = null
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
    const group = groups.get(day)
    if (group) group.push(photo)
    else groups.set(day, [photo])
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
  photoTime: photo.photo_time,
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
async function load() {
  loading.value = true
  try {
    memory.value = await memoryApi.detail(String(route.params.id))
    scheduleStoryPoll()
  }
  catch { ElMessage.error('加载记忆失败') }
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
function openPhoto(id: string) {
  photoTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  lightboxIndex.value = lightboxImages.value.findIndex(photo => photo.id === id)
}
function closePhoto() {
  lightboxIndex.value = -1
  const trigger = photoTrigger
  photoTrigger = null
  void nextTick(() => trigger?.focus({ preventScroll: true }))
}

function scrollToMemorySection(element: HTMLElement | null) {
  element?.focus({ preventScroll: true })
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  element?.scrollIntoView({ behavior: reduceMotion ? 'instant' : 'smooth', block: 'start' })
}

function jumpToTimeline() { scrollToMemorySection(photoTimeline.value) }
function jumpToDay(day: string) { scrollToMemorySection(document.getElementById(`memory-day-${day}`)) }
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

<style scoped>
.memory-spread-page { width: 100%; max-width: 1540px; min-height: 100%; margin-inline: auto; padding: 14px var(--ts-page-gutter) 38px; }
.memory-spread-controls, .memory-spread-tools { display: flex; align-items: center; gap: 8px; }
.memory-spread-controls { justify-content: space-between; margin-bottom: 14px; }
.memory-tool { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 44px; min-height: 44px; padding: 0 12px; border: 1px solid var(--ts-color-border); border-radius: 999px; background: var(--ts-color-surface); color: var(--ts-color-text); white-space: nowrap; font-size: 13px; font-weight: 600; transition: background-color 180ms ease; }
.memory-tool:hover, .memory-tool[aria-pressed='true'] { background: var(--ts-color-surface-muted); }
.memory-tool:disabled { cursor: wait; opacity: .6; }
.memory-tool--primary { background: var(--ts-journal-action); color: white; border-color: transparent; }
.memory-tool--primary:hover { background: var(--ts-journal-action-hover); }
.memory-tool svg { width: 16px; height: 16px; flex-shrink: 0; }
.memory-tool:focus-visible, .memory-story-write:focus-visible, .memory-day-nav button:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 2px; }
.memory-spread-cover, .memory-spread-skeleton { min-height: clamp(270px, 30vw, 440px); border-radius: 24px; }
.memory-spread-skeleton { background: var(--ts-color-surface-muted); }
.memory-spread-error { display: grid; justify-items: center; gap: 14px; padding: 48px 16px; border: 1px dashed var(--ts-color-border); border-radius: 18px; }
.memory-spread-cover { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr); overflow: hidden; border: 1px solid var(--ts-color-border); background: linear-gradient(135deg, var(--ts-journal-active), transparent 60%), var(--ts-color-surface); color: var(--ts-color-text); }
.memory-spread-heading { display: flex; flex-direction: column; justify-content: center; gap: 12px; min-width: 0; padding: clamp(20px, 4vw, 56px); }
.memory-spread-heading h1 { font: 700 clamp(34px, 4.8vw, 64px)/1.13 var(--ts-journal-serif); letter-spacing: -.05em; overflow-wrap: anywhere; }
.memory-spread-date, .memory-spread-places { display: flex; align-items: center; gap: 7px; color: var(--ts-color-text-secondary); font-size: 13px; overflow-wrap: anywhere; }
.memory-spread-date svg, .memory-spread-places svg { width: 15px; height: 15px; flex-shrink: 0; color: var(--ts-journal-accent-text); }
.memory-spread-places { align-items: flex-start; }
.memory-spread-places ul { display: flex; flex-wrap: wrap; gap: 3px 8px; min-width: 0; }
.memory-spread-places li + li::before { content: '·'; margin-right: 8px; color: var(--ts-journal-accent-text); }
.memory-spread-heading-actions { margin-top: 5px; }
.memory-spread-heading-actions:empty { display: none; }
.memory-spread-image { position: relative; display: grid; place-items: center; min-width: 0; background: radial-gradient(ellipse at 70% 30%, #495b77, #1e293b 72%); }
.memory-spread-image img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.memory-spread-placeholder { width: 52px; height: 52px; color: var(--ts-journal-on-image); stroke-width: 1; }
.memory-spread-review { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-top: 14px; padding: 10px 13px; border-radius: 14px; background: var(--ts-journal-active); color: var(--ts-color-text); font-size: 13px; }
.memory-spread-review > span { display: inline-flex; align-items: baseline; flex-wrap: wrap; gap: 7px 10px; }
.memory-spread-content { display: grid; grid-template-columns: minmax(0, 1fr); gap: clamp(20px, 3vw, 46px); margin-top: 24px; }
.memory-spread-primary { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; }
.memory-story { padding: clamp(16px, 2.5vw, 34px); border-radius: 18px; border: 1px solid var(--ts-color-border); background: var(--ts-color-surface); }
.memory-spread-section-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; }
.memory-spread-section-heading h2 { font: 700 clamp(23px, 2.5vw, 33px)/1.18 var(--ts-journal-serif); }
.memory-story-text { max-width: 64ch; margin-top: 13px; color: var(--ts-color-text-secondary); font-size: 15px; line-height: 1.9; white-space: pre-wrap; overflow-wrap: anywhere; }
.memory-story-write { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; margin-top: 9px; color: var(--ts-color-text-secondary); font-size: 14px; }
button.memory-story-write:hover { color: var(--ts-color-text); }
.memory-story-write svg { width: 15px; height: 15px; }
.memory-photo-timeline, .memory-day { scroll-margin-top: 14px; }
.memory-photo-timeline:focus-visible, .memory-day:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 4px; }
.memory-day-nav { display: flex; gap: 6px; overflow: auto hidden; margin-top: 12px; padding-bottom: 4px; scrollbar-width: thin; }
.memory-day-nav button { flex-shrink: 0; min-height: 44px; padding-inline: 13px; border-radius: 999px; background: var(--ts-journal-rail); color: var(--ts-color-text); font-weight: 550; font-size: 12px; }
.memory-day-nav button:hover { background: var(--ts-journal-active); }
.memory-day-nav button:focus-visible { outline-offset: -3px; }
.memory-day { padding: 14px 0 4px; border-top: 1px solid var(--ts-color-border); margin-top: 17px; }
.memory-day-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 10px; }
.memory-day-heading h3 { font-size: 15px; font-weight: 650; }
.memory-day-heading span { color: var(--ts-color-text-secondary); font-size: 12px; }
.memory-photo-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.memory-photo-grid--single { grid-template-columns: minmax(0, 460px); }
.memory-photo { position: relative; aspect-ratio: 1; overflow: hidden; border-radius: 12px; background: var(--ts-color-surface-muted); }
.memory-photo-grid--single .memory-photo { aspect-ratio: 1.6; }
.memory-photo img { width: 100%; height: 100%; object-fit: cover; transition: transform 380ms cubic-bezier(.22,.61,.36,1); }
.memory-photo:hover img { transform: scale(1.055); }
.memory-photo:focus-visible { outline: 3px solid var(--ts-journal-on-image); outline-offset: -4px; }
.memory-photo-play, .memory-photo-selected { position: absolute; right: 7px; top: 7px; width: 29px; height: 29px; padding: 6px; border-radius: 50%; background: rgb(15 23 42 / 68%); color: white; }
.memory-photo-selected { right: auto; left: 7px; }
.memory-photo-selected > svg { width: 100%; height: 100%; }
.memory-photo[aria-pressed='true'] .memory-photo-selected { background: var(--ts-journal-action); color: white; }
.memory-selected-dock { position: sticky; bottom: 12px; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px; padding: 8px 12px; border-radius: 14px; color: var(--ts-color-text); background: var(--ts-color-surface-raised); border: 1px solid var(--ts-color-border); box-shadow: var(--ts-shadow-floating); }
.memory-spread-notes { align-self: start; border: 1px solid var(--ts-color-border); border-radius: 16px; padding: 0 17px; background: var(--ts-journal-rail); }
.memory-spread-notes section { padding-block: 16px; }
.memory-spread-notes section + section { border-top: 1px solid var(--ts-color-divider); }
.memory-spread-notes h2 { display: flex; align-items: center; gap: 7px; font-weight: 700; }
.memory-spread-notes h2 svg { width: 15px; height: 15px; color: var(--ts-journal-focus); }
.memory-spread-notes ul { display: grid; gap: 8px; margin-top: 10px; color: var(--ts-color-text-secondary); font-size: 13px; overflow-wrap: anywhere; }
.memory-spread-notes small { margin-left: 6px; color: var(--ts-color-text-tertiary); }
@media (min-width: 1080px) { .memory-spread-content:has(.memory-spread-notes) { grid-template-columns: minmax(0, 1fr) minmax(205px, 25%); } }
@media (max-width: 767px) {
  .memory-spread-page { padding-top: 10px; }
  .memory-spread-controls { margin-bottom: 9px; }
  .memory-tool--wide, .memory-spread-tools .memory-tool span { display: none; }
  .memory-spread-cover { grid-template-columns: minmax(0, 1fr); border-radius: 18px; }
  .memory-spread-heading { grid-row: 2; padding: 17px 18px 20px; gap: 8px; }
  .memory-spread-heading h1 { font-size: clamp(29px, 8vw, 41px); }
  .memory-spread-image { aspect-ratio: 1.68; }
  .memory-photo-grid:not(.memory-photo-grid--single) { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; }
  .memory-photo { border-radius: 8px; }
  .memory-selected-dock { bottom: calc(var(--ts-tabbar-h) + var(--ts-safe-area-bottom)); }
}
@media (prefers-reduced-motion: reduce) { .memory-tool, .memory-photo img { transition: none; } }
</style>
