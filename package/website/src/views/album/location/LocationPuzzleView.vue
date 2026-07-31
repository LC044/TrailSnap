<template>
  <div class="location-puzzle flex flex-col md:flex-row w-full h-full">
    <!-- 左侧拼图画布 -->
    <div class="flex-1 relative overflow-hidden bg-gray-50 dark:bg-gray-900 h-[50vh] md:h-full">
      <!-- 加载遮罩 -->
      <div
        v-if="loading"
        class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-gray-50/80 dark:bg-gray-900/80 backdrop-blur-sm"
      >
        <span
          class="w-8 h-8 rounded-full border-[3px] border-primary-500 border-t-transparent animate-spin"
        />
        <p class="text-sm text-gray-500 dark:text-gray-400">正在生成拼图…</p>
      </div>

      <!-- 错误态 -->
      <div
        v-else-if="error"
        class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 px-6 text-center"
      >
        <ImageOff class="w-10 h-10 text-gray-300 dark:text-gray-600" />
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ error }}</p>
        <button
          class="px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="reload"
        >
          重新加载
        </button>
      </div>

      <!-- 空态 -->
      <div
        v-else-if="!loading && !cells.length"
        class="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 px-6 text-center"
      >
        <MapPin class="w-10 h-10 text-gray-300 dark:text-gray-600" />
        <p class="text-sm text-gray-500 dark:text-gray-400">
          还没有带位置信息的照片，无法生成拼图
        </p>
      </div>

      <PuzzleCanvas
        ref="canvasRef"
        :geometries="geometries"
        :cells="cells"
        :assignments="assignments"
        :region-counts="regionCounts"
        :show-label="config.showLabel"
        :interactive="true"
        :thumbnail-size="scope === 'nation' ? 'small' : 'medium'"
        @select-region="handleSelectRegion"
        @select-cell="handleSelectCell"
        @resize="resize"
      />

      <!-- 返回全国按钮（单省模式，浮在画布左上） -->
      <button
        v-if="scope === 'province'"
        class="absolute top-3 left-3 z-20 px-3 py-1.5 rounded-lg bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm shadow-md text-sm text-gray-700 dark:text-gray-200 hover:bg-white dark:hover:bg-gray-800 transition-colors flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @click="handleDrillUp"
      >
        <ChevronLeft class="w-4 h-4" />
        全国
      </button>
    </div>

    <!-- 右侧配置面板 -->
    <div
      class="w-full md:w-80 lg:w-96 flex flex-col bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-t md:border-t-0 md:border-l border-gray-200 dark:border-gray-700 h-[50vh] md:h-full z-10"
    >
      <el-scrollbar class="flex-1">
        <div class="p-4 md:p-6">
          <PuzzlePanel
            :scope="scope"
            :active-province="activeProvince"
            :config="config"
            :cell-count="cells.length"
            :used-photo-count="usedPhotoCount"
            :region-counts="regionCounts"
            :loading="loading"
            @update-config="handleUpdateConfig"
            @drill-down="handleSelectRegion"
            @drill-up="handleDrillUp"
            @reshuffle="reshuffle"
          />
        </div>
      </el-scrollbar>
    </div>

    <!-- 格子换图操作弹层 -->
    <el-dialog
      v-model="cellDialogVisible"
      title="调整这个位置"
      width="320px"
      align-center
      append-to-body
    >
      <div class="flex flex-col gap-3">
        <img
          v-if="activeCellPhotoUrl"
          :src="activeCellPhotoUrl"
          alt="当前照片"
          class="w-full aspect-square object-cover rounded-lg"
        />
        <div v-else class="w-full aspect-square rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-sm text-gray-400">
          这个位置是空的
        </div>
        <div class="flex gap-2">
          <button
            class="flex-1 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="handleReplaceCell"
          >
            换一张
          </button>
          <button
            class="flex-1 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="handleRemoveCell"
          >
            留空
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ImageOff, MapPin } from 'lucide-vue-next'
import PuzzleCanvas from './components/PuzzleCanvas.vue'
import PuzzlePanel from './components/PuzzlePanel.vue'
import { useMapPuzzle, type PuzzleConfig } from '@/composables/useMapPuzzle'

const props = defineProps<{
  startDate?: string
  endDate?: string
}>()

const canvasRef = ref<InstanceType<typeof PuzzleCanvas> | null>(null)

const {
  scope,
  activeProvince,
  config,
  loading,
  error,
  geometries,
  cells,
  assignments,
  regionCounts,
  usedPhotoCount,
  loadNation,
  drillDown,
  drillUp,
  resize,
  recompute,
  replaceCellPhoto,
  removeCellPhoto,
  reshuffle,
} = useMapPuzzle()

// --- 格子编辑 ---
const cellDialogVisible = ref(false)
const activeCellIndex = ref<number | null>(null)

const activeCellPhotoUrl = computed(() => {
  if (activeCellIndex.value === null) return null
  const id = assignments.value[activeCellIndex.value]
  return id ? `/api/medias/${id}/thumbnail?size=medium` : null
})

const handleSelectRegion = async (name: string) => {
  // 全国图点省下钻；单省图点自身不做处理（交由格子命中逻辑）
  if (scope.value !== 'nation') return
  const count = regionCounts.value.get(name) ?? 0
  if (count <= 0) return
  await drillDown(name, props.startDate, props.endDate)
}

const handleSelectCell = (index: number) => {
  // 仅单省模式允许编辑，全国图格子太小没有意义
  if (scope.value !== 'province') return
  activeCellIndex.value = index
  cellDialogVisible.value = true
}

const handleReplaceCell = () => {
  if (activeCellIndex.value === null) return
  replaceCellPhoto(activeCellIndex.value)
}

const handleRemoveCell = () => {
  if (activeCellIndex.value === null) return
  removeCellPhoto(activeCellIndex.value)
  cellDialogVisible.value = false
}

const handleDrillUp = async () => {
  await drillUp(props.startDate, props.endDate)
}

const handleUpdateConfig = (patch: Partial<PuzzleConfig>) => {
  const needRecompute = 'targetCount' in patch
  const needReload = 'strategy' in patch
  config.value = { ...config.value, ...patch }

  if (needReload) {
    reload()
  } else if (needRecompute) {
    recompute()
  }
  // showLabel 只影响绘制，由 PuzzleCanvas 内部 watch 自动重绘
}

const reload = async () => {
  if (scope.value === 'province' && activeProvince.value) {
    await drillDown(activeProvince.value, props.startDate, props.endDate)
  } else {
    await loadNation(props.startDate, props.endDate)
  }
}

// 日期筛选变化时重新加载
watch(
  () => [props.startDate, props.endDate],
  () => reload()
)

onMounted(() => {
  loadNation(props.startDate, props.endDate)
})
</script>
