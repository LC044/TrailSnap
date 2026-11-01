<template>
  <ResponsiveDialog v-model="visible" title="失败任务" :description="title" max-width="56rem" mobile-mode="fullscreen" mobile-back :glass="false">
    <div v-if="loading" class="py-16 text-center ts-muted" role="status">正在加载失败任务…</div>
    <div v-else-if="loadError" class="py-12 text-center">
      <p class="ts-muted mb-4">失败任务加载失败</p>
      <button class="ts-button ts-button-secondary" @click="loadTasks">重新加载</button>
    </div>
    <div v-else-if="!tasks.length" class="py-16 text-center ts-muted">没有失败任务</div>
    <div v-else class="failure-list">
      <p class="text-sm ts-muted">{{ tasks.length }} 个失败任务{{ tasks.length === 1000 ? '（最多显示 1000 条）' : '' }}</p>
      <article v-for="task in shownTasks" :key="task.id" class="failure-card">
        <div class="flex items-start gap-3 min-w-0">
          <button class="failure-photo" :disabled="!photoId(task) || previewing === task.id" :aria-label="`查看照片：${filename(task)}`" @click="viewPhoto(task)">
            <img v-if="photos[photoId(task)] && !brokenImages.has(task.id)" :src="thumbnailUrl(photoId(task), 'small', photos[photoId(task)].owner_id)" alt="" loading="lazy" @error="brokenImages.add(task.id)" />
            <ImageOff v-else class="h-6 w-6 ts-muted" />
          </button>
          <div class="min-w-0 flex-1">
            <h3 class="font-semibold break-words">{{ filename(task) }}</h3>
            <p class="text-xs ts-muted mt-1">{{ taskType(task) }} · {{ formatTime(task.created_at) }}</p>
            <details v-if="filePath(task)" class="failure-path">
              <summary>文件路径</summary>
              <p>{{ filePath(task) }}</p>
            </details>
            <p v-else class="failure-path">{{ photoId(task) ? '照片路径暂不可用' : '此任务未关联已入库照片' }}</p>
          </div>
        </div>
        <details class="failure-error">
          <summary><span class="failure-summary">{{ errorSummary(task) }}</span><span class="shrink-0 text-xs primary-text">错误详情</span></summary>
          <pre tabindex="0" aria-label="完整错误信息">{{ task.error || '未记录错误信息' }}</pre>
        </details>
        <div class="failure-actions">
          <button class="ts-button ts-button-secondary ts-button-sm" :disabled="!task.error || copying.has(task.id)" @click="copyErrorLog(task)"><Copy class="h-4 w-4" />{{ copying.has(task.id) ? '复制中…' : '复制日志' }}</button>
          <button v-if="photoId(task)" class="ts-button ts-button-secondary ts-button-sm" :disabled="previewing === task.id" @click="viewPhoto(task)"><ImageIcon class="h-4 w-4" />{{ previewing === task.id ? '加载中…' : '查看照片' }}</button>
          <button v-if="isTauriApp() && (filePath(task) || photoId(task))" class="ts-button ts-button-secondary ts-button-sm" :disabled="revealing.has(task.id)" @click="revealPhoto(task)"><FolderOpen class="h-4 w-4" />打开所在文件夹</button>
          <button class="ts-button ts-button-primary ts-button-sm" :disabled="retrying.has(task.id)" @click="retryTask(task)"><RotateCw class="h-4 w-4" />{{ retrying.has(task.id) ? '重试中…' : '重试' }}</button>
        </div>
      </article>
      <button v-if="shownTasks.length < tasks.length" class="ts-button ts-button-secondary w-full" @click="showMore">加载更多（剩余 {{ tasks.length - shownTasks.length }} 项）</button>
    </div>
  </ResponsiveDialog>
  <PhotoLightbox v-if="preview" :visible="true" :image="preview" @close="preview = null" />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Copy, FolderOpen, Image as ImageIcon, ImageOff, RotateCw } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { tasksApi, type Task } from '@/api/tasks'
import { albumService } from '@/api/album'
import { revealDesktopPhoto } from '@/api/desktopDataDirectory'
import { isTauriApp } from '@/config/server'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { copyTextToClipboard } from '@/utils/clipboard'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { AlbumImage, Photo } from '@/types/album'

const PhotoLightbox = defineAsyncComponent(() => import('@/components/PhotoLightbox.vue'))
const props = defineProps<{ modelValue: boolean; category: string; title: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; retried: [] }>()
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const tasks = ref<Task[]>([])
const loading = ref(false)
const loadError = ref(false)
const photos = ref<Record<string, Photo>>({})
const brokenImages = ref(new Set<string>())
const retrying = ref(new Set<string>())
const revealing = ref(new Set<string>())
const copying = ref(new Set<string>())
const previewing = ref<string | null>(null)
const preview = ref<AlbumImage | null>(null)
const pageSize = ref(20)
const shownTasks = computed(() => tasks.value.slice(0, pageSize.value))
let generation = 0
const photoId = (task: Task): string => typeof task.payload?.photo_id === 'string' ? task.payload.photo_id : ''
const filePath = (task: Task): string => photos.value[photoId(task)]?.file_path || (typeof task.payload?.file_path === 'string' ? task.payload.file_path : '')
const filename = (task: Task) => photos.value[photoId(task)]?.filename || filePath(task).split(/[\\/]/).pop() || '未关联照片的任务'
const taskType = (task: Task) => props.title || task.type
const formatTime = (value: string) => Number.isNaN(Date.parse(value)) ? '时间未知' : new Date(value).toLocaleString('zh-CN')
const errorSummary = (task: Task) => (task.error || '未记录错误信息').split(/\r?\n/)[0].slice(0, 180)
const copyErrorLog = async (task: Task) => {
  if (!task.error || copying.value.has(task.id)) return
  copying.value.add(task.id)
  try {
    if (await copyTextToClipboard(task.error)) ElMessage.success('错误日志已复制')
    else ElMessage.error('复制失败，请展开错误详情手动复制')
  } finally { copying.value.delete(task.id) }
}

const hydratePhotos = async (version: number) => {
  const ids = [...new Set(shownTasks.value.map(photoId).filter(id => id && !photos.value[id]))]
  if (!ids.length) return
  try {
    const result = await albumService.getPhotosByIds(ids)
    if (version !== generation) return
    for (const photo of result) photos.value[photo.id] = photo
  } catch { /* Photo lookup is optional; explicit preview reports a failure and can retry. */ }
}
const loadTasks = async () => {
  const version = ++generation
  loading.value = true
  loadError.value = false
  tasks.value = []
  photos.value = {}
  brokenImages.value.clear()
  pageSize.value = 20
  try {
    const result = await tasksApi.listTasks('failed', props.category, 1000)
    if (version !== generation) return
    tasks.value = result
    void hydratePhotos(version)
  } catch { if (version === generation) loadError.value = true }
  finally { if (version === generation) loading.value = false }
}
const showMore = () => { pageSize.value += 20; void hydratePhotos(generation) }
const resolvePhoto = async (task: Task) => {
  const id = photoId(task)
  if (!id) throw new Error('任务尚未关联已入库照片')
  // Refresh on explicit actions so deleted photos and unavailable permissions are respected.
  const photo = (await albumService.getPhotosByIds([id])).find(item => item.id === id)
  if (!photo) throw new Error('照片不存在、已删除或无权访问')
  return photo
}
const viewPhoto = async (task: Task) => {
  if (previewing.value) return
  const version = generation
  previewing.value = task.id
  try {
    const photo = await resolvePhoto(task)
    if (version === generation && visible.value) preview.value = mapPhotoToImage(photo)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '照片加载失败，请重试') }
  finally { previewing.value = null }
}
const revealPhoto = async (task: Task) => {
  if (!isTauriApp() || revealing.value.has(task.id)) return
  revealing.value.add(task.id)
  try {
    const photo = photoId(task) ? await resolvePhoto(task) : null
    const path = photo?.file_path || (photo ? (await albumService.getMetadata(photo.id)).file_path : filePath(task))
    if (!path) throw new Error('照片路径不可用')
    await revealDesktopPhoto(path)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : String(error || '打开文件夹失败')) }
  finally { revealing.value.delete(task.id) }
}
const retryTask = async (task: Task) => {
  if (retrying.value.has(task.id)) return
  retrying.value.add(task.id)
  const version = generation
  try {
    await tasksApi.retryTask(task.id)
    if (version === generation) {
      tasks.value = tasks.value.filter(item => item.id !== task.id)
      void hydratePhotos(version)
    }
    emit('retried')
    ElMessage.success('已加入重试队列')
  } catch { ElMessage.error('重试失败，请稍后再试') }
  finally { retrying.value.delete(task.id) }
}
watch(() => [props.modelValue, props.category] as const, ([open]) => {
  if (open) void loadTasks()
  else { generation++; preview.value = null }
}, { immediate: true })
</script>

<style scoped>
.failure-list { display: grid; gap: 16px; min-width: 0; }
.failure-card { min-width: 0; padding: 16px; border: 1px solid var(--ts-color-border); border-radius: 18px; background: var(--ts-color-surface); }
.failure-photo { display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 64px; height: 64px; overflow: hidden; border-radius: 12px; background: var(--ts-color-surface-muted); }
.failure-photo img { width: 100%; height: 100%; object-fit: cover; }
.failure-photo:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 3px; }
.failure-path { margin-top: 6px; color: var(--ts-color-text-secondary); font-size: 12px; overflow-wrap: anywhere; }
.failure-path summary { cursor: pointer; }
.failure-path p { margin-top: 6px; }
.failure-card h3 { overflow-wrap: anywhere; }
.failure-error { min-width: 0; margin-top: 14px; padding: 12px; border-radius: 12px; background: var(--ts-color-surface-muted); }
.failure-error summary { display: flex; align-items: center; gap: 12px; cursor: pointer; list-style: none; }
.failure-error summary::-webkit-details-marker { display: none; }
.failure-summary { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.primary-text { color: var(--theme-primary); }
.failure-error pre { max-height: 40dvh; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; margin-top: 12px; font-size: 12px; line-height: 1.65; }
.failure-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 14px; }
@media (max-width: 767px) {
  .failure-card { padding: 14px; }
  .failure-actions .ts-button { min-height: 44px; flex: 1 1 auto; }
}
</style>
