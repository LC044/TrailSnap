<template>
  <el-dialog
    v-model="dialogVisible"
    title="批量修正位置"
    width="900px"
    destroy-on-close
    :close-on-click-modal="false"
    align-center
    append-to-body
    @opened="initBatchMap"
    @closed="destroyBatchMap"
  >
    <div class="flex gap-4 h-[500px]">
      <div class="flex-1 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-100 relative">
        <div id="batch-location-map" class="w-full h-full"></div>
        <div v-if="mapLoading" class="absolute inset-0 flex items-center justify-center bg-gray-100/80 dark:bg-gray-800/80">
          <Loader2 class="w-6 h-6 animate-spin text-primary-500" />
        </div>
        <div v-if="mapError" class="absolute inset-0 flex items-center justify-center bg-gray-100 dark:bg-gray-800">
          <p class="text-sm text-gray-500">地图加载失败，请检查地图 API 配置</p>
        </div>
      </div>

      <div class="w-64 flex flex-col gap-3">
        <div class="text-sm text-gray-500 dark:text-gray-400">
          已选 <span class="font-bold text-gray-900 dark:text-white">{{ photoIds.length }}</span> 张照片
        </div>

        <el-autocomplete
          v-model="searchQuery"
          :fetch-suggestions="handleSearch"
          placeholder="搜索地点"
          @select="handleSelect"
          class="w-full"
          :trigger-on-focus="false"
        >
          <template #default="{ item }">
            <div class="flex flex-col leading-tight py-1">
              <span class="font-medium text-sm">{{ item.value }}</span>
              <span class="text-xs text-gray-500">{{ item.address }}</span>
            </div>
          </template>
        </el-autocomplete>

        <div class="text-xs text-gray-500 space-y-1">
          <p>经度: {{ currentMapLng ? currentMapLng.toFixed(6) : '--' }}</p>
          <p>纬度: {{ currentMapLat ? currentMapLat.toFixed(6) : '--' }}</p>
          <p v-if="batchLocationDetail?.address" class="text-gray-600 dark:text-gray-400 truncate" :title="batchLocationDetail.address">{{ batchLocationDetail.address }}</p>
        </div>

        <el-input v-model="formattedAddress" placeholder="自定义地址（留空使用自动解析）" size="small" />

        <div class="flex-1 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-white dark:bg-gray-900">
          <div class="grid grid-cols-3 gap-1">
            <div v-for="photo in photos" :key="photo.id" class="aspect-square rounded overflow-hidden">
              <img
                :src="photo.thumbnail"
                class="w-full h-full object-cover"
                :alt="photo.filename"
                loading="lazy"
              />
            </div>
          </div>
        </div>

        <p class="text-xs text-gray-400">拖拽地图标记选择位置</p>
      </div>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false" :disabled="submitting">取消</el-button>
        <el-button type="primary" @click="handleApply" :loading="submitting" :disabled="!currentMapLat && !currentMapLng">
          应用到全部 ({{ photoIds.length }})
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import { useLocationMap, type LocationDetail } from '@/composables/useLocationMap'
import { albumService } from '@/api/album'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AlbumImage } from '@/types/album'

const props = defineProps<{
  modelValue: boolean
  photoIds: string[]
  photos: AlbumImage[]
}>()

const emit = defineEmits(['update:modelValue', 'success'])

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const mapLoading = ref(false)
const submitting = ref(false)
const searchQuery = ref('')
const formattedAddress = ref('')
const batchLocationDetail = ref<LocationDetail | null>(null)

const {
  currentLat: currentMapLat,
  currentLng: currentMapLng,
  currentLocationDetail,
  mapReady,
  mapError,
  initMap,
  setMarker,
  enableMarkerDrag,
  searchLocation,
  searchAndSelect,
  destroy: destroyMap
} = useLocationMap({
  onPositionChange: (_lat: number, _lng: number, detail?: LocationDetail) => {
    batchLocationDetail.value = detail || null
  }
})

const initBatchMap = async () => {
  mapLoading.value = true
  await initMap({
    containerId: 'batch-location-map',
    enableDrag: true
  })
  mapLoading.value = false
}

const destroyBatchMap = () => {
  destroyMap()
  searchQuery.value = ''
  formattedAddress.value = ''
  batchLocationDetail.value = null
}

const handleSearch = (query: string, cb: (results: any[]) => void) => {
  searchLocation(query, cb)
}

const handleSelect = (item: any) => {
  searchAndSelect(item.value)
}

const handleApply = async () => {
  if (!currentMapLat.value && !currentMapLng.value) {
    ElMessage.warning('请先在地图上选择位置')
    return
  }

  if (props.photoIds.length > 50) {
    try {
      await ElMessageBox.confirm(
        `即将修改 ${props.photoIds.length} 张照片的位置，是否继续？`,
        '确认批量修改',
        { type: 'warning' }
      )
    } catch {
      return
    }
  }

  submitting.value = true
  try {
    const detail = batchLocationDetail.value || currentLocationDetail.value
    await albumService.batchUpdateLocation(
      props.photoIds,
      currentMapLat.value,
      currentMapLng.value,
      formattedAddress.value || detail?.address || undefined,
      detail
    )
    ElMessage.success(`已更新 ${props.photoIds.length} 张照片的位置`)
    dialogVisible.value = false
    emit('success')
  } catch (error) {
    console.error('Batch location update failed', error)
    ElMessage.error('批量更新位置失败')
  } finally {
    submitting.value = false
  }
}
</script>
