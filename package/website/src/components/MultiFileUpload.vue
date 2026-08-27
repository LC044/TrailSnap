<template>
  <div class="w-full">
    <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end">
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
      class="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl p-8 text-center hover:border-primary-500 dark:hover:border-primary-500 transition-colors cursor-pointer relative"
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
        accept="image/*,video/*" 
        @change="handleFileSelect"
      />
      <div class="flex flex-col items-center justify-center gap-3">
        <div class="w-12 h-12 bg-primary-50 text-primary-500 rounded-full flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        </div>
        <div class="text-gray-600 dark:text-gray-300 font-medium">
          点击或拖拽上传图片/视频
        </div>
        <div class="text-xs text-gray-400">
          支持 JPG, PNG, GIF, MP4 (最大 100MB)
        </div>
      </div>
    </div>

    <div v-if="files.length > 0" class="mt-6 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
      <div class="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-t-lg flex justify-between items-center">
        <h3 class="font-medium text-gray-900 dark:text-white">待上传列表 ({{ files.length }})</h3>
        <span v-if="isProcessingFiles" class="text-xs text-primary-500 animate-pulse">正在加载更多文件...</span>
      </div>
      
      <div class="max-h-96 overflow-y-auto p-4 space-y-3 scroll-smooth">
        <div 
          v-for="(file, index) in files" 
          :key="file.id" 
          class="bg-white dark:bg-gray-800 rounded-lg p-3 flex items-center gap-4 shadow-sm border border-gray-100 dark:border-gray-700"
        >
          <div class="w-12 h-12 rounded-md overflow-hidden bg-gray-100 flex-shrink-0">
            <img v-if="file.preview" :src="file.preview" class="w-full h-full object-cover" loading="lazy" />
            <div v-else class="w-full h-full flex items-center justify-center text-gray-400">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
            </div>
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex justify-between items-center mb-1">
              <p class="text-sm font-medium text-gray-900 dark:text-white truncate" :title="file.raw.name">{{ file.raw.name }}</p>
              <button @click="removeFile(index)" class="text-gray-400 hover:text-red-500" :disabled="uploading">
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
              <span class="text-xs text-gray-500">{{ formatSize(file.raw.size) }}</span>
              <span 
                class="text-xs"
                :class="{
                  'text-gray-500': file.status === 'pending',
                  'text-primary-500': file.status === 'uploading',
                  'text-green-500': file.status === 'success',
                  'text-red-500': file.status === 'error'
                }"
              >
                {{ getStatusText(file.status) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="sticky bottom-0 bg-white dark:bg-gray-900 p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3 rounded-b-lg">
        <button 
          @click="clearFiles" 
          class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          :disabled="uploading || isProcessingFiles"
        >
          清空
        </button>
        <button 
          @click="startUpload" 
          class="px-4 py-2 text-sm bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors shadow-lg shadow-primary-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="uploading || isProcessingFiles || files.length === 0"
        >
          {{ uploading ? '上传中...' : '开始上传' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { albumService } from '@/api/album'

const props = defineProps<{
  albumId?: string
}>()

const emit = defineEmits<{
  (e: 'upload-complete'): void
}>()

interface UploadFile {
  id: string // 增加唯一ID，优化 v-for key 性能
  raw: File
  preview?: string
  objectURL?: string
  progress: number
  status: 'pending' | 'uploading' | 'success' | 'error'
}

const fileInput = ref<HTMLInputElement | null>(null)
const files = ref<UploadFile[]>([])
const uploading = ref(false)
const selectedFolder = ref('')
const uploadFolders = ref<string[]>([])
const externalUploadFolders = ref<string[]>([])

const loadUploadFolders = async () => {
  try {
    const result = await albumService.getUploadFolders()
    uploadFolders.value = result.folders
    externalUploadFolders.value = result.externalFolders
  } catch (error) {
    console.error('加载上传文件夹失败:', error)
  }
}

const createFolder = async () => {
  try {
    const { value } = await ElMessageBox.prompt(
      '可输入多级路径，例如“家人/小明”',
      '新建上传文件夹',
      {
        confirmButtonText: '创建',
        cancelButtonText: '取消',
        inputPattern: /^(?![\\/])(?!.*(?:^|[\\/])\.\.?($|[\\/]))[^:*?"<>|]+$/,
        inputErrorMessage: '请输入安全的相对文件夹路径',
      },
    )
    const path = await albumService.createUploadFolder(value.trim())
    await loadUploadFolders()
    selectedFolder.value = path
    ElMessage.success('文件夹已创建')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('创建文件夹失败')
    }
  }
}

// 优化：处理状态追踪
const isProcessingFiles = ref(false)
const processedCount = ref(0)
const totalFilesToProcess = ref(0)

const triggerFileInput = () => {
  if (uploading.value || isProcessingFiles.value) return
  fileInput.value?.click()
}

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    // 转换为数组
    processFilesBatched(Array.from(input.files))
  }
  input.value = ''
}

const handleDrop = (event: DragEvent) => {
  if (uploading.value || isProcessingFiles.value) return
  const droppedFiles = event.dataTransfer?.files
  if (droppedFiles && droppedFiles.length > 0) {
    processFilesBatched(Array.from(droppedFiles))
  }
}

/**
 * 核心优化：分片处理文件，避免UI卡死
 */
const processFilesBatched = async (newFiles: File[]) => {
  const MAX_SIZE = 100 * 1024 * 1024 // 100MB
  const validFiles: File[] = []

  // 1. 快速预筛选（此步很快，可以同步）
  newFiles.forEach(file => {
    if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) {
      // 这里的 alert 如果文件多会很烦，建议改成 console.warn 或统一提示
      console.warn(`跳过文件 ${file.name}: 格式不支持`)
      return
    }
    if (file.size > MAX_SIZE) {
      console.warn(`跳过文件 ${file.name}: 超过 100MB`)
      return
    }
    validFiles.push(file)
  })

  if (validFiles.length === 0) return

  // 2. 初始化处理状态
  isProcessingFiles.value = true
  totalFilesToProcess.value = validFiles.length
  processedCount.value = 0

  // 3. 分批处理配置
  const CHUNK_SIZE = 20 // 每次处理20个文件，保证60fps
  let index = 0

  const processChunk = () => {
    const chunk = validFiles.slice(index, index + CHUNK_SIZE)
    
    // 如果没有更多文件，结束处理
    if (chunk.length === 0) {
      isProcessingFiles.value = false
      return
    }

    // 处理当前批次
    const newUploadFiles: UploadFile[] = chunk.map(file => {
      let previewURL: string | undefined = undefined
      let objectURL: string | undefined = undefined
      
      try {
        objectURL = URL.createObjectURL(file)
        previewURL = objectURL
      } catch (e) {
        console.error('生成预览失败:', e)
      }

      return {
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`, // 生成唯一key
        raw: file,
        preview: previewURL,
        objectURL: objectURL,
        progress: 0,
        status: 'pending'
      }
    })

    // 批量推入数组，触发 Vue 更新
    files.value.push(...newUploadFiles)
    
    // 更新进度
    index += CHUNK_SIZE
    processedCount.value = Math.min(index, validFiles.length)

    // 使用 requestAnimationFrame 让出主线程，允许浏览器渲染 UI 后再处理下一批
    if (index < validFiles.length) {
      requestAnimationFrame(processChunk)
    } else {
      isProcessingFiles.value = false
    }
  }

  // 开始处理第一批
  processChunk()
}

/**
 * 移除单个文件
 */
const removeFile = (index: number) => {
  const file = files.value[index]
  if (file.objectURL) {
    URL.revokeObjectURL(file.objectURL)
  }
  files.value.splice(index, 1)
}

/**
 * 清空所有文件
 */
const clearFiles = () => {
  files.value.forEach(file => {
    if (file.objectURL) {
      URL.revokeObjectURL(file.objectURL)
    }
  })
  files.value = []
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const getStatusText = (status: UploadFile['status']) => {
  switch (status) {
    case 'pending': return '等待上传'
    case 'uploading': return '上传中...'
    case 'success': return '上传成功'
    case 'error': return '上传失败'
    default: return ''
  }
}

/**
 * 开始上传 (带有简单的并发控制，避免同时请求过多)
 */
const startUpload = async () => {
  if (files.value.length === 0 || uploading.value) return
  
  uploading.value = true
  
  // 简单的并发控制：一次上传 3 个，避免浏览器卡死
  const CONCURRENCY = 3
  const pendingFiles = files.value.filter(f => f.status !== 'success')
  
  const uploadFileItem = async (file: UploadFile) => {
    file.status = 'uploading'
    file.progress = 0
    try {
      if (file.raw.size > 5 * 1024 * 1024) {
        await uploadChunked(file)
      } else {
        await albumService.uploadPhoto(file.raw, props.albumId, selectedFolder.value || undefined)
        file.progress = 100
      }
      file.status = 'success'
    } catch (error) {
      console.error('上传失败:', error)
      file.status = 'error'
    }
  }

  // 队列处理函数
  const queue = [...pendingFiles]
  const workers = Array(Math.min(CONCURRENCY, queue.length)).fill(null).map(async () => {
    while (queue.length > 0) {
      const file = queue.shift()
      if (file) await uploadFileItem(file)
    }
  })

  await Promise.all(workers)

  uploading.value = false
  emit('upload-complete')
}

const uploadChunked = async (file: UploadFile) => {
  const CHUNK_SIZE = 1 * 1024 * 1024 
  const totalChunks = Math.ceil(file.raw.size / CHUNK_SIZE)
  const uploadId = await albumService.initUpload()

  for (let i = 0; i < totalChunks; i++) {
    if (file.status === 'error') break 

    const start = i * CHUNK_SIZE
    const end = Math.min(start + CHUNK_SIZE, file.raw.size)
    const chunk = file.raw.slice(start, end)
    
    await albumService.uploadChunk(uploadId, i, chunk)
    file.progress = Math.round(((i + 1) / totalChunks) * 100)
  }

  await albumService.finishUpload(uploadId, file.raw.name, props.albumId, selectedFolder.value || undefined)
}

onMounted(loadUploadFolders)

onUnmounted(() => {
  files.value.forEach(file => {
    if (file.objectURL) {
      URL.revokeObjectURL(file.objectURL)
    }
  })
})
</script>
