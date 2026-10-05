<template>
  <div class="mx-auto w-full max-w-4xl px-[var(--ts-page-gutter)] py-6">
    <div class="flex items-center gap-4 mb-6">
      <BackButton label="返回工具箱" @click="goBack" />
      <div>
        <h1 class="ts-page-title text-gray-800 dark:text-white">修改图片元数据</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">选择目录或相册，批量修改其中照片的拍摄信息。操作会直接修改原始文件元数据且不可逆。</p>
      </div>
    </div>

    <TaskStatusCard :task="activeTask" processing-label="处理中" :clearing="clearing" @clear="clearFailedTask" />

    <!-- Configuration Form -->
    <div class="ts-surface p-6">
      <el-form label-position="top" :disabled="isTaskRunning">
        <el-form-item label="处理范围" required>
          <el-radio-group v-model="targetType" class="mb-3 w-full">
            <el-radio value="folder">存储目录</el-radio>
            <el-radio value="album">相册</el-radio>
          </el-radio-group>
          <div v-if="targetType === 'folder'" class="flex items-center gap-4 w-full">
            <el-input 
              v-model="targetRootPath" 
              placeholder="请选择要进行操作的文件夹" 
              readonly
              class="flex-1"
            >
              <template #prepend>
                <Folder class="w-4 h-4" />
              </template>
            </el-input>
            <el-button type="primary" plain @click="showFolderSelector = true">选择目录</el-button>
          </div>
          <button v-else type="button" :disabled="isTaskRunning" class="flex min-h-14 w-full items-center gap-3 rounded-lg border border-gray-300 bg-white p-2 text-left hover:border-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800" @click="openAlbumSelector">
            <span v-if="selectedAlbum" class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-primary-50 text-primary-500 dark:bg-primary-900/30">
              <img v-if="selectedAlbum.cover?.id" :src="thumbnailUrl(selectedAlbum.cover.id, 'small', selectedAlbum.cover.owner_id)" :alt="`${selectedAlbum.name}的封面`" class="h-full w-full object-cover" />
              <Folder v-else class="h-5 w-5" />
            </span>
            <span class="min-w-0 flex-1 truncate text-sm" :class="selectedAlbum ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'">{{ selectedAlbum ? `${selectedAlbum.name}（${selectedAlbum.num_photos} 个项目）` : '请选择相册' }}</span>
            <span class="shrink-0 text-sm text-primary-600 dark:text-primary-400">{{ selectedAlbum ? '更换' : '选择相册' }}</span>
          </button>
          <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ targetType === 'folder' ? '将处理该目录及子目录中已入库的照片。' : '只处理选中相册内的照片，照片原有存储位置不变。' }}支持可写入 EXIF 的图片格式。</div>
        </el-form-item>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <el-form-item label="拍摄品牌（Make）">
            <el-input v-model="make" placeholder="例如: Apple, Samsung, Canon" clearable />
            <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">选填，将同步更新到照片的设备品牌信息</div>
          </el-form-item>

          <el-form-item label="拍摄型号（Model）">
            <el-input v-model="model" placeholder="例如: iPhone 15, Galaxy S24" clearable />
            <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">选填，将同步更新到照片的设备型号信息</div>
          </el-form-item>
        </div>

        <el-form-item label="拍摄时间处理方式" subtitle="选择如何处理照片的拍摄时间字段">
          <el-radio-group v-model="timeMode" class="flex flex-col items-start gap-3">
            <el-radio value="auto" class="!mr-0 !ml-0">自动识别</el-radio>
            <div class="flex items-center gap-2">
              <el-radio value="custom" class="!mr-0 !ml-0">指定时间</el-radio>
              <el-date-picker
                v-if="timeMode === 'custom'"
                v-model="customTime"
                type="datetime"
                placeholder="选择日期和时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </div>
            <el-radio value="none" class="!mr-0 !ml-0">不修改时间（仅修改设备信息）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="onlyMissingMetadata">仅修改元数据缺失的图片</el-checkbox>
          <div class="text-xs text-gray-500 mt-1 dark:text-gray-400">勾选后，仅对缺少拍摄设备信息（品牌、型号）的照片进行修改，否则对所有照片强制进行修改（包括已存在品牌、型号的照片）。
          <br><span class="text-red-500">注意：如果照片已存在品牌、型号信息，勾选后将不会修改。</span></div>
        </el-form-item>

        <div class="flex justify-end mt-8">
          <el-button 
            type="primary" 
            size="large" 
            :loading="starting" 
            :disabled="!(targetType === 'folder' ? targetRootPath : targetAlbumId) || isTaskRunning"
            @click="startProcess"
          >
            开始修改拍摄信息
          </el-button>
        </div>
      </el-form>
    </div>

    <!-- Folder Selection Dialog -->
    <DirectoryPickerDialog v-model:visible="showFolderSelector" v-model="targetRootPath" />


    <AlbumSelector
      v-model:visible="showAlbumSelector"
      mode="select"
      :selection-albums="albums"
      :selected-album-id="targetAlbumId"
      :loading="albumsLoading"
      @select="targetAlbumId = $event"
    />

  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { ref, computed } from 'vue'
import TaskStatusCard from '@/components/TaskStatusCard.vue'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
import { useTaskMonitor } from '@/composables/useTaskMonitor'
import { useAppBack } from '@/composables/useAppBack'
import { Folder } from 'lucide-vue-next'
import { toolboxApi } from '@/api/toolbox'
import { albumService } from '@/api/album'
import type { ApiAlbum } from '@/types/album'
import { useUserStore } from '@/stores/user'
import { thumbnailUrl } from '@/utils/mediaUrl'
import AlbumSelector from '@/components/AlbumSelector.vue'
import { ElMessage } from 'element-plus'

const goBack = useAppBack('/toolbox')
const userStore = useUserStore()

const targetRootPath = ref('')
const targetType = ref<'folder' | 'album'>('folder')
const targetAlbumId = ref('')
const albums = ref<ApiAlbum[]>([])
const albumsLoading = ref(false)
const starting = ref(false)
const onlyMissingMetadata = ref(true)
const make = ref('')
const model = ref('')
const timeMode = ref('auto')
const customTime = ref('')

const showFolderSelector = ref(false)
const showAlbumSelector = ref(false)
const selectedAlbum = computed(() => albums.value.find(album => album.id === targetAlbumId.value))

const openAlbumSelector = () => {
  showAlbumSelector.value = true
  loadAlbums()
}

const loadAlbums = async () => {
  if (albumsLoading.value) return
  albumsLoading.value = true
  try {
    const result: ApiAlbum[] = []
    let page: ApiAlbum[]
    do {
      page = await albumService.getAlbums(result.length, 100)
      result.push(...page)
    } while (page.length === 100)
    albums.value = result.filter(album => album.owner_id === userStore.userInfo?.id)
  } catch {
    ElMessage.error('加载相册失败')
  } finally {
    albumsLoading.value = false
  }
}


const { activeTask, isTaskRunning, clearing, clearFailedTask: clearTask } = useTaskMonitor({
  loadLatest: () => toolboxApi.getLatestTimeFromFilenameTask(),
  taskType: 'BATCH_TIME_FROM_FILENAME',
  onCompleted: () => ElMessage.success('批量修改拍摄信息已完成'),
  onError: error => console.error('Failed to monitor task', error),
})

const clearFailedTask = async () => {
  try { await clearTask(); ElMessage.success('已清除失败任务') }
  catch { ElMessage.error('清除任务失败') }
}

const startProcess = async () => {
  if (targetType.value === 'folder' ? !targetRootPath.value : !targetAlbumId.value) {
    ElMessage.warning('请选择目标目录或相册')
    return
  }

  if (timeMode.value === 'custom' && !customTime.value) {
    ElMessage.warning('请选择具体的日期和时间')
    return
  }
  
  starting.value = true
  try {
    const payload: Parameters<typeof toolboxApi.createTimeFromFilenameTask>[0] = {
      ...(targetType.value === 'folder' ? { target_root_path: targetRootPath.value } : { album_id: targetAlbumId.value }),
      only_missing_metadata: onlyMissingMetadata.value,
      time_mode: timeMode.value
    }
    if (timeMode.value === 'custom' && customTime.value) {
      payload.custom_time = customTime.value
    }
    if (make.value) {
      payload.make = make.value
    }
    if (model.value) {
      payload.model = model.value
    }
    const task = await toolboxApi.createTimeFromFilenameTask(payload)
    activeTask.value = task
    ElMessage.success('已开始修改拍摄信息任务')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建任务失败')
  } finally {
    starting.value = false
  }
}

</script>
