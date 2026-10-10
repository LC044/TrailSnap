<template>
  <div class="w-full min-h-0 flex flex-col">
    <div class="mb-4 shrink-0 flex flex-col gap-2 sm:flex-row sm:items-end">
      <label class="flex-1 text-sm text-gray-700 dark:text-gray-300">
        <span class="mb-1 block font-medium">上传到文件夹</span>
        <el-select v-model="selectedFolder" class="w-full" placeholder="按年月自动整理" clearable filterable :disabled="uploading">
          <el-option label="按年月自动整理" value="" />
          <el-option-group v-if="uploadFolders.length" label="用户上传目录">
            <el-option v-for="folder in uploadFolders" :key="folder" :label="folder" :value="folder" />
          </el-option-group>
          <el-option-group v-if="externalUploadFolders.length" label="外部挂载目录">
            <el-option v-for="folder in externalUploadFolders" :key="folder" :label="folder" :value="folder" />
          </el-option-group>
        </el-select>
      </label>
      <button
        type="button"
        class="rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:border-primary-500 hover:text-primary-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        :disabled="uploading"
        @click="createFolder"
      >
        新建文件夹
      </button>
    </div>
    <div 
      class="shrink-0 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl text-center hover:border-primary-500 dark:hover:border-primary-500 transition-colors cursor-pointer relative"
      :class="files.length ? 'px-4 py-3' : 'p-8'"
      role="button" tabindex="0" :aria-disabled="uploading || isProcessingFiles"
      @keydown.enter.prevent="triggerFileInput" @keydown.space.prevent="triggerFileInput"
      @click="triggerFileInput"
      @drop.prevent="handleDrop"
      @dragover.prevent
      @dragenter.prevent
    >
      <div v-if="isProcessingFiles" class="absolute inset-0 bg-white/80 dark:bg-gray-800/80 flex items-center justify-center z-10 rounded-xl">
        <div class="flex flex-col items-center">
          <svg class="animate-spin h-8 w-8 text-primary-500 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-sm text-gray-600 dark:text-gray-300">正在解析文件 ({{ processedCount }}/{{ totalFilesToProcess }})</span>
        </div>
      </div>

      <input 
        type="file" 
        ref="fileInput" 
        class="hidden" 
        multiple 
        :accept="MEDIA_ACCEPT"
        @change="handleFileSelect"
      />
      <div v-if="!files.length" class="flex flex-col items-center justify-center gap-3">
        <div class="w-12 h-12 bg-primary-50 text-primary-500 rounded-full flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        </div>
        <div class="text-gray-600 dark:text-gray-300 font-medium">
          点击或拖拽上传图片/视频
        </div>
        <div class="text-xs text-gray-400 dark:text-gray-500">
          支持 HEIC / HEIF、JPG、PNG、GIF、WebP、TIFF，以及 MP4、MOV 等视频
        </div>
      </div>
      <div v-else class="flex flex-wrap justify-center gap-x-3 gap-y-1 text-sm text-gray-600 dark:text-gray-300">
        <span>添加更多照片 / 视频</span><span class="text-xs self-center">原文件无损上传 · 无大小限制</span>
      </div>
    </div>

    <div v-if="files.length > 0" class="mt-4 min-h-0 flex flex-col border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
      <div class="p-4 shrink-0 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-t-lg flex justify-between items-center">
        <h3 class="font-medium text-gray-900 dark:text-white">上传队列 ({{ files.length }})</h3>
        <span v-if="isProcessingFiles" class="text-xs text-primary-500 animate-pulse">正在加载更多文件...</span>
      </div>
      <div class="px-4 py-3 shrink-0 text-xs text-gray-600 dark:text-gray-300 space-y-2" aria-live="polite">
        <div class="flex flex-wrap justify-between gap-2">
          <span>已完成 {{ counts.success }} · 处理中 {{ counts.checking + counts.uploading + counts.finalizing }} · 等待 {{ counts.pending }} · 失败 {{ counts.error }}</span>
          <span>{{ formatSize(uploadedBytes) }} / {{ formatSize(totalBytes) }}<template v-if="uploading && speed > 0"> · {{ formatSize(speed) }}/s</template></span>
        </div>
        <el-progress :percentage="overallProgress" :stroke-width="6" :show-text="false" />
        <p v-if="rejectedCount" class="text-red-600 dark:text-red-400">已跳过 {{ rejectedCount }} 个不支持的格式或空文件。</p>
      </div>
      <div ref="listContainer" class="max-h-96 min-h-0 overflow-y-auto px-4" @scroll="handleListScroll">
        <div class="relative" :style="{ height: `${files.length * windowRange.rowHeight}px` }">
        <div class="absolute inset-x-0" :style="{ top: `${windowRange.start * windowRange.rowHeight}px` }">
        <div 
          v-for="file in visibleFiles"
          :key="file.id" 
          class="h-20 bg-white dark:bg-gray-800 rounded-lg p-3 flex items-center gap-3 shadow-sm border border-gray-100 dark:border-gray-700"
          style="margin-bottom: 8px"
        >
          <div class="w-12 h-12 rounded-md overflow-hidden bg-gray-100 dark:bg-gray-700 flex-shrink-0">
            <img v-if="file.preview" :src="file.preview" alt="文件预览" class="w-full h-full object-cover" loading="lazy" @error="clearPreview(file)" />
            <div v-else class="w-full h-full flex items-center justify-center text-gray-400 dark:text-gray-500">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
            </div>
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex justify-between items-center mb-1">
              <p class="text-sm font-medium text-gray-900 dark:text-white truncate min-w-0" :title="file.raw.name">{{ file.raw.name }}</p>
              <button @click="removeFileById(file.id)" :aria-label="`移除 ${file.raw.name}`" class="text-gray-400 dark:text-gray-500 hover:text-red-500 shrink-0" :disabled="uploading || isProcessingFiles">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
              </button>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-1.5 dark:bg-gray-700 overflow-hidden">
              <div 
                class="bg-primary-500 h-1.5 rounded-full transition-all duration-300"
                :style="{ width: `${file.progress}%` }"
                :class="{
                  'bg-green-500': file.status === 'success',
                  'bg-red-500': file.status === 'error'
                }"
              ></div>
            </div>
            <div class="flex justify-between mt-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ formatSize(file.raw.size) }}</span>
              <span 
                class="text-xs truncate ml-2" :title="file.error || getStatusText(file.status)"
                :class="{
                  'text-gray-500 dark:text-gray-400': file.status === 'pending',
                  'text-primary-500': ['checking', 'uploading', 'finalizing'].includes(file.status),
                  'text-green-500': file.status === 'success',
                  'text-red-500': file.status === 'error'
                }"
              >
                {{ file.error || getStatusText(file.status) }}
              </span>
            </div>
          </div>
        </div>
        </div>
        </div>
      </div>

      <div class="shrink-0 bg-white dark:bg-gray-900 p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3 rounded-b-lg">
        <button v-if="uploading" type="button" @click="controller?.abort()"
          class="px-4 py-2 text-sm text-red-600 dark:text-red-400 rounded-lg">停止上传</button>
        <button 
          @click="clearFiles" 
          class="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          :disabled="uploading || isProcessingFiles"
        >
          清空
        </button>
        <button 
          @click="startUpload" 
          class="px-4 py-2 text-sm bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors shadow-lg shadow-primary-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="uploading || isProcessingFiles || counts.pending + counts.error === 0"
        >
          {{ uploading ? '上传中...' : counts.error > 0 ? '重试未完成文件' : '开始上传' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { albumService } from '@/api/album'
import { getServerUrl } from '@/config/server'
import { isLanServerUrl } from '@/utils/backupTransfer'
import { MEDIA_ACCEPT, isSupportedMedia, manualTransferSettings, uploadWindow, uploadStreamingChunks } from '@/utils/manualUpload'

const props = defineProps<{ albumId?: string }>()
const emit = defineEmits<{
  (e: 'upload-complete'): void
  (e: 'upload-state', state: { running: boolean; completed: number; total: number; failed: number; progress: number }): void
}>()
type UploadStatus = 'pending' | 'checking' | 'uploading' | 'finalizing' | 'success' | 'error'
interface UploadFile {
  id: string
  raw: File
  preview?: string
  previewFailed?: boolean
  progress: number
  uploadedBytes: number
  status: UploadStatus
  error?: string
}
const emptyCounts = () => ({ pending: 0, checking: 0, uploading: 0, finalizing: 0, success: 0, error: 0 })
const fileInput = ref<HTMLInputElement | null>(null)
const listContainer = ref<HTMLElement | null>(null)
const files = ref<UploadFile[]>([])
const counts = ref(emptyCounts())
const uploading = ref(false)
const selectedFolder = ref('')
const uploadFolders = ref<string[]>([])
const externalUploadFolders = ref<string[]>([])
const isProcessingFiles = ref(false)
const processedCount = ref(0)
const totalFilesToProcess = ref(0)
const rejectedCount = ref(0)
const totalBytes = ref(0)
const uploadedBytes = ref(0)
const speed = ref(0)
const scrollTop = ref(0)
const viewportHeight = ref(384)
const windowRange = computed(() => uploadWindow(files.value.length, scrollTop.value, viewportHeight.value))
const visibleFiles = computed(() => files.value.slice(windowRange.value.start, windowRange.value.end))
const overallProgress = computed(() => totalBytes.value ? Math.min(counts.value.success === files.value.length ? 100 : 99, Math.floor(uploadedBytes.value / totalBytes.value * 100)) : 0)
watch([uploading, () => counts.value.success, () => counts.value.error, () => files.value.length, overallProgress], () => {
  emit('upload-state', { running: uploading.value, completed: counts.value.success, total: files.value.length, failed: counts.value.error, progress: overallProgress.value })
}, { immediate: true })
let destroyed = false
let processingTimer: ReturnType<typeof setTimeout> | undefined
let speedTimer: ReturnType<typeof setInterval> | undefined
let controller: AbortController | undefined
let nextId = 0
const previewFiles = new Set<UploadFile>()
let previewRunning = false

const setStatus = (file: UploadFile, status: UploadStatus) => {
  counts.value[file.status]--
  file.status = status
  counts.value[status]++
}
const clearPreview = (file: UploadFile) => {
  if (file.preview) URL.revokeObjectURL(file.preview)
  file.preview = undefined
  previewFiles.delete(file)
}
// Only mounted rows receive URLs. Large originals/HEIC/videos use placeholders
// to avoid decoding hundreds of full-resolution files just to show a queue.
watch(visibleFiles, async visible => {
  const current = new Set(visible)
  for (const file of previewFiles) if (!current.has(file)) clearPreview(file)
  if (previewRunning || typeof createImageBitmap !== 'function') return
  previewRunning = true
  try {
    while (!destroyed) {
      const file = visibleFiles.value.find(item => !item.preview && !item.previewFailed && item.raw.size <= 12 * 1024 * 1024 && /\.(jpe?g|png|webp|gif)$/i.test(item.raw.name))
      if (!file) break
      file.previewFailed = true
      // Decode at most one preview at a time and retain only a 96px bitmap.
      // The raw File used for hashing/uploading remains untouched.
      try {
        const bitmap = await createImageBitmap(file.raw, { resizeWidth: 96, resizeHeight: 96, resizeQuality: 'low' })
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = 96
        canvas.getContext('2d')?.drawImage(bitmap, 0, 0)
        bitmap.close()
        const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.7))
        if (blob && !destroyed && visibleFiles.value.includes(file)) {
          file.preview = URL.createObjectURL(blob)
          previewFiles.add(file)
        }
      } catch { /* Unsupported browser decoding uses the file placeholder. */ }
    }
  } finally {
    previewRunning = false
  }
})
const handleListScroll = (event: Event) => {
  const element = event.currentTarget as HTMLElement
  scrollTop.value = element.scrollTop
  viewportHeight.value = element.clientHeight
}
const loadUploadFolders = async () => {
  try {
    const result = await albumService.getUploadFolders()
    if (destroyed) return
    uploadFolders.value = result.folders
    externalUploadFolders.value = result.externalFolders
  } catch (error) { console.error('加载上传文件夹失败:', error) }
}
const createFolder = async () => {
  try {
    const { value } = await ElMessageBox.prompt('可输入多级路径，例如“家人/小明”', '新建上传文件夹', {
      confirmButtonText: '创建', cancelButtonText: '取消',
      inputPattern: /^(?![\\/])(?!.*(?:^|[\\/])\.\.?($|[\\/]))[^:*?"<>|]+$/,
      inputErrorMessage: '请输入安全的相对文件夹路径',
    })
    const path = await albumService.createUploadFolder(value.trim())
    await loadUploadFolders()
    selectedFolder.value = path
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('创建文件夹失败')
  }
}
const triggerFileInput = () => {
  if (!uploading.value && !isProcessingFiles.value) fileInput.value?.click()
}
const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!uploading.value && !isProcessingFiles.value && input.files?.length) processFilesBatched(Array.from(input.files))
  input.value = ''
}
const handleDrop = (event: DragEvent) => {
  if (!uploading.value && !isProcessingFiles.value && event.dataTransfer?.files.length) processFilesBatched(Array.from(event.dataTransfer.files))
}
const processFilesBatched = (newFiles: File[]) => {
  isProcessingFiles.value = true
  processedCount.value = 0
  rejectedCount.value = 0
  totalFilesToProcess.value = newFiles.length
  let index = 0
  const processBatch = () => {
    if (destroyed) return
    const end = Math.min(newFiles.length, index + 100)
    const items: UploadFile[] = []
    for (; index < end; index++) {
      const raw = newFiles[index]!
      if (!isSupportedMedia(raw) || raw.size === 0) { rejectedCount.value++; continue }
      items.push({ id: String(nextId++), raw, progress: 0, uploadedBytes: 0, status: 'pending' })
      totalBytes.value += raw.size
      counts.value.pending++
    }
    files.value.push(...items)
    processedCount.value = index
    if (index < newFiles.length) processingTimer = setTimeout(processBatch, 0)
    else {
      isProcessingFiles.value = false
      if (rejectedCount.value) ElMessage.warning(`已跳过 ${rejectedCount.value} 个不支持的格式或空文件`)
    }
  }
  processBatch()
}
const removeFileById = (id: string) => {
  if (uploading.value || isProcessingFiles.value) return
  const index = files.value.findIndex(file => file.id === id)
  if (index < 0) return
  const file = files.value[index]!
  clearPreview(file)
  counts.value[file.status]--
  totalBytes.value -= file.raw.size
  uploadedBytes.value -= file.uploadedBytes
  files.value.splice(index, 1)
}
const clearFiles = () => {
  for (const file of previewFiles) clearPreview(file)
  files.value = []
  counts.value = emptyCounts()
  totalBytes.value = uploadedBytes.value = scrollTop.value = rejectedCount.value = 0
  listContainer.value?.scrollTo({ top: 0 })
}
const formatSize = (bytes: number) => {
  if (bytes <= 0) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${Number((bytes / 1024 ** index).toFixed(2))} ${sizes[index]}`
}
const getStatusText = (status: UploadStatus) => ({
  pending: '等待上传', checking: '准备上传', uploading: '校验并上传原文件', finalizing: '服务器校验与保存', success: '原文件已保存 · 校验通过', error: '上传失败',
})[status]

const startUpload = async () => {
  if (uploading.value || isProcessingFiles.value || !counts.value.pending && !counts.value.error) return
  uploading.value = true
  controller = new AbortController()
  const signal = controller.signal
  const tuning = manualTransferSettings(isLanServerUrl(getServerUrl() || import.meta.env.VITE_API_BASE_URL || window.location.origin))
  const pending = files.value.filter(file => file.status !== 'success')
  const folder = selectedFolder.value || undefined
  let next = 0
  let succeeded = 0
  let previousBytes = uploadedBytes.value
  speedTimer = setInterval(() => {
    speed.value = Math.max(0, uploadedBytes.value - previousBytes)
    previousBytes = uploadedBytes.value
  }, 1000)
  const uploadItem = async (file: UploadFile) => {
    let uploadId: string | undefined
    file.error = undefined
    uploadedBytes.value -= file.uploadedBytes
    file.uploadedBytes = file.progress = 0
    setStatus(file, 'checking')
    try {
      uploadId = await albumService.initUpload({ signal, silentError: true })
      setStatus(file, 'uploading')
      let lastUpdate = 0
      const integrity = await uploadStreamingChunks(file.raw, tuning.chunkSize, tuning.chunkConcurrency, signal,
        async (index, chunk, sha256, report) => {
          for (let attempt = 0; ; attempt++) {
            try {
              await albumService.uploadChunk(uploadId!, index, chunk, loaded => report(Math.min(chunk.size, loaded)), { signal, sha256, silentError: true })
              return
            } catch (error: any) {
              if (signal.aborted || attempt >= 2 || error.response?.status && ![408, 429, 500, 502, 503, 504].includes(error.response.status)) throw error
              report(0)
              await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt))
              signal.throwIfAborted()
            }
          }
        }, loaded => {
          const now = performance.now()
          if (now - lastUpdate < 100 && loaded !== file.raw.size) return
          lastUpdate = now
          uploadedBytes.value += loaded - file.uploadedBytes
          file.uploadedBytes = loaded
          file.progress = Math.min(99, Math.floor(loaded / file.raw.size * 100))
        })
      setStatus(file, 'finalizing')
      await albumService.finishUpload(uploadId, file.raw.name, props.albumId, folder, undefined, false, undefined, undefined, { integrity, signal, silentError: true })
      setStatus(file, 'success')
      file.progress = 100
      succeeded++
    } catch (error: any) {
      setStatus(file, 'error')
      file.error = signal.aborted ? '上传已停止' : error.response?.data?.detail || error.message || '上传失败，请重试'
      if (uploadId) await albumService.discardUpload(uploadId).catch(() => {})
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(tuning.fileConcurrency, pending.length) }, async () => {
      while (!signal.aborted) {
        const index = next++
        if (index >= pending.length) break
        await uploadItem(pending[index]!)
      }
    }))
    if (!destroyed) {
      if (succeeded) emit('upload-complete')
      if (counts.value.error) ElMessage.warning(`${counts.value.error} 个文件上传失败，可重试未完成文件`)
      else if (signal.aborted) ElMessage.info('上传已停止，未完成文件可重试')
      else ElMessage.success('全部原文件已保存，照片整理将在后台继续')
    }
  } finally {
    clearInterval(speedTimer)
    speed.value = 0
    uploading.value = false
    controller = undefined
  }
}
onMounted(loadUploadFolders)
onUnmounted(() => {
  destroyed = true
  controller?.abort()
  clearTimeout(processingTimer)
  clearInterval(speedTimer)
  for (const file of previewFiles) clearPreview(file)
})
</script>
