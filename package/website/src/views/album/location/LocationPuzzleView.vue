<template>
  <div class="location-puzzle flex flex-col md:flex-row w-full h-full relative">
    <!-- 左侧拼图画布（移动端撑满，抽屉浮于其上） -->
    <!-- min-h-0 让 flex-1 在移动端 flex-col 下正确分配高度，避免 h-full 百分比链
         在 overflow-y-auto 的 flex 父容器内解析为 0（移动端 Safari 真机表现），
         导致 ResizeObserver 测得 0 高 → setup() 跳过 → 画布空白 -->
    <div class="flex-1 min-h-0 relative overflow-hidden bg-gray-50 dark:bg-gray-900 md:h-full">
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
        :show-label="config.showLabel && scope !== 'province'"
        :scope="scope"
        :interactive="true"
        :thumbnail-size="scope === 'nation' ? 'small' : 'medium'"
        @select-region="handleSelectRegion"
        @select-cell="handleSelectCell"
        @resize="resize"
      />

      <!-- 面包屑导航（单省模式，浮在画布左上，与地图视图保持一致） -->
      <div
        v-if="scope === 'province'"
        class="absolute top-6 left-6 z-20 flex items-center gap-2 bg-white/90 dark:bg-gray-800/90 backdrop-blur-md px-3 py-2 rounded-xl shadow-md border border-gray-200 dark:border-gray-700 animate-fade-in"
      >
        <button
          class="p-1 -ml-1 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-primary-500 dark:hover:text-primary-400 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          title="返回全国"
          @click="handleDrillUp"
        >
          <ArrowLeft class="w-4 h-4" />
        </button>
        <div class="w-px h-4 bg-gray-300 dark:bg-gray-600" />
        <button
          class="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-primary-500 dark:hover:text-primary-400 transition-colors flex items-center gap-1 px-1 rounded-lg focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="handleDrillUp"
        >
          <MapPin class="w-4 h-4" />
          全国
        </button>
        <ChevronRight class="w-4 h-4 text-gray-400" />
        <span class="text-sm font-bold text-gray-800 dark:text-white pr-1">{{ activeProvince }}</span>
      </div>
    </div>

    <!-- 右侧配置面板：移动端为 fixed 底部抽屉（peek/expand），桌面端为侧栏 -->
    <div
      class="fixed md:static inset-x-0 bottom-[calc(var(--ts-tabbar-h)+env(safe-area-inset-bottom))] md:inset-auto z-30 md:z-auto flex flex-col h-auto md:h-full md:w-80 lg:w-96 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md border-t md:border-t-0 md:border-l border-gray-200 dark:border-gray-700 rounded-t-2xl md:rounded-none shadow-2xl md:shadow-sm transition-[height] duration-300 ease-out"
      :class="{ '!transition-none': isDragging }"
      :style="isMobile ? { height: sheetHeight + 'px' } : {}"
    >
      <!-- 拖拽手柄区（仅移动端：点击切换 peek/expand，拖拽连续调高度） -->
      <div
        class="md:hidden shrink-0 h-8 flex items-center justify-center cursor-grab active:cursor-grabbing touch-none select-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @pointerdown="onHandlePointerDown"
        @click="onHandleClick"
        @keydown.enter="onHandleClick"
        @keydown.space.prevent="onHandleClick"
        role="button"
        tabindex="0"
        aria-label="拖动调整配置面板高度"
      >
        <div class="w-10 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
      </div>

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
        <div class="flex gap-2 flex-wrap">
          <!-- 主操作：手动模式选照片；自动模式从该省照片池换一张 -->
          <button
            v-if="config.strategy === 'manual'"
            class="flex-1 min-w-[7rem] py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="openManualPicker"
          >
            选择照片
          </button>
          <button
            v-else
            class="flex-1 min-w-[7rem] py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="handleReplaceCell"
          >
            换一张
          </button>
          <!-- 自动模式：选择照片（选完自动切到手动模式） -->
          <button
            v-if="config.strategy !== 'manual'"
            class="flex-1 min-w-[5rem] py-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="openManualPicker"
          >
            选择照片
          </button>
          <!-- 手动模式：留空（也是一种手选意图，会持久化） -->
          <button
            v-else
            class="flex-1 min-w-[5rem] py-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="handleRemoveCell"
          >
            留空
          </button>
          <!-- 手动模式且该格已有手选覆盖：可恢复自动 -->
          <button
            v-if="
              config.strategy === 'manual' &&
              activeCellIndex !== null &&
              manualAssignments[String(activeCellIndex)] !== undefined
            "
            class="flex-1 min-w-[5rem] py-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="handleClearManualCell"
          >
            恢复自动
          </button>
        </div>
      </div>
    </el-dialog>

    <!-- 手动选择照片全屏 Picker（复用相册「添加照片」选择器） -->
    <Transition name="slide-up">
      <div
        v-if="manualPickerVisible"
        class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm md:p-4"
        @click.self="closeManualPicker"
      >
        <div
          class="bg-white dark:bg-gray-900 md:rounded-2xl shadow-2xl w-full h-full md:max-w-7xl md:h-[90vh] overflow-hidden flex flex-col"
        >
          <!-- 顶部切换：默认只展示当前省份，可一键切到全库 -->
          <div
            class="flex items-center gap-2 px-4 py-2 border-b border-gray-100 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md"
          >
            <span class="text-xs text-gray-500 dark:text-gray-400">展示范围：</span>
            <button
              class="px-3 py-1 rounded-full text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              :class="
                pickerScope === 'province'
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              "
              @click="setPickerScope('province')"
            >
              仅{{ activeProvince ?? '本省' }}
            </button>
            <button
              class="px-3 py-1 rounded-full text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              :class="
                pickerScope === 'all'
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              "
              @click="setPickerScope('all')"
            >
              全部照片
            </button>
          </div>
          <!-- :key 让切换展示范围时 PhotoSelector 重新挂载，重新按新过滤条件加载 -->
          <PhotoSelector
            :key="pickerScope"
            :is-selector="true"
            :store="selectionStore"
            :title="`为「${activeProvince ?? ''}」选择照片`"
            @select="handleManualPick"
            @cancel="closeManualPicker"
          />
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, ChevronRight, ImageOff, MapPin } from 'lucide-vue-next'
import PuzzleCanvas from './components/PuzzleCanvas.vue'
import PuzzlePanel from './components/PuzzlePanel.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import { useSelectionStore } from '@/stores/selectionStore'
import { useMapPuzzle, type PuzzleConfig } from '@/composables/useMapPuzzle'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { toServerUrl } from '@/config/server'
import { thumbnailUrl } from '@/utils/mediaUrl'

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
  setManualCell,
  clearManualCell,
  manualAssignments,
  reshuffle,
} = useMapPuzzle()

// --- 手动选择照片 ---
const selectionStore = useSelectionStore()
const manualPickerVisible = ref(false)
const manualPickerCellIndex = ref<number | null>(null)

// --- 格子编辑 ---
const cellDialogVisible = ref(false)
const activeCellIndex = ref<number | null>(null)

const activeCellPhotoUrl = computed(() => {
  if (activeCellIndex.value === null) return null
  const id = assignments.value[activeCellIndex.value]
  return id ? thumbnailUrl(id, 'medium') : null
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
  // 手动模式：留空也是一种手选意图，需要持久化
  if (config.value.strategy === 'manual') {
    setManualCell(activeCellIndex.value, null)
  } else {
    removeCellPhoto(activeCellIndex.value)
  }
  cellDialogVisible.value = false
}

// --- 手动选择 ---
// 默认只展示当前省份照片，可切到全库。provinceFilter 与全局 selectedFilters 解耦，
// 不写入持久化缓存，关掉选择器即清空，避免污染相册主列表的筛选状态。
const pickerScope = ref<'province' | 'all'>('province')

const openManualPicker = () => {
  if (activeCellIndex.value === null) return
  manualPickerCellIndex.value = activeCellIndex.value
  cellDialogVisible.value = false
  pickerScope.value = 'province'
  selectionStore.provinceFilter = activeProvince.value
  manualPickerVisible.value = true
}

const setPickerScope = (scope: 'province' | 'all') => {
  if (pickerScope.value === scope) return
  pickerScope.value = scope
  // PhotoSelector 用 :key 重新挂载，重新加载前先把过滤条件设好
  selectionStore.provinceFilter = scope === 'province' ? activeProvince.value : null
}

const closeManualPicker = () => {
  manualPickerVisible.value = false
  // 清掉瞬时省份过滤，避免 selectionStore 复用时残留
  selectionStore.provinceFilter = null
}
useOverlayStack(manualPickerVisible, closeManualPicker)

// PhotoSelector 是多选，手动填格只取一张 —— 沿用 ProfileSettings.vue 头像选择的 ids[0] 约定
const handleManualPick = (ids: string[]) => {
  if (ids.length === 0) return
  if (manualPickerCellIndex.value === null) {
    closeManualPicker()
    return
  }
  // 自动模式下首次手选：自动切到手动模式。
  // 不走 reload（reload 会清掉 manualAssignments 再从空 localStorage 重建，丢失本次选择），
  // 而是先切策略、再 setManualCell 直接覆盖当前 assignments 并落盘——
  // 后续 recompute 时 manualAssignments 已有值，overlay 能正确套用。
  if (config.value.strategy !== 'manual') {
    config.value = { ...config.value, strategy: 'manual' }
  }
  setManualCell(manualPickerCellIndex.value, ids[0])
  closeManualPicker()
}

const handleClearManualCell = () => {
  if (activeCellIndex.value === null) return
  clearManualCell(activeCellIndex.value)
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

/* ----------------------- 移动端底部抽屉：peek / expand ----------------------- */
// 桌面端为侧栏（md:static md:h-full），sheetHeight 仅移动端生效（内联高度门控 isMobile）。
// 拼图面板是恒定配置（无选中态驱动），故无自动展开 watch，仅手动 peek/expand。
const PEEK_H = 128                                   // 收起态：露手柄 + 标题 + 统计卡
const expandedH = () => Math.min(                    // 展开态：~70vh，但至少留 header + 120px 画布可点
  Math.round(window.innerHeight * 0.7),
  window.innerHeight - 240
)
const sheetHeight = ref(PEEK_H)
const isDragging = ref(false)
let dragMoved = false
let dragOrigin = { startY: 0, startH: 0 }

const clampSheetH = (h: number) => Math.max(PEEK_H, Math.min(h, expandedH()))

const onHandlePointerDown = (e: PointerEvent) => {
  if (e.button !== 0) return
  dragOrigin = { startY: e.clientY, startH: sheetHeight.value }
  isDragging.value = true
  dragMoved = false
  window.addEventListener('pointermove', onHandlePointerMove)
  window.addEventListener('pointerup', onHandlePointerUp)
}

const onHandlePointerMove = (e: PointerEvent) => {
  if (!isDragging.value) return
  const dy = e.clientY - dragOrigin.startY
  if (Math.abs(dy) > 3) dragMoved = true
  // 上拖 dy<0 → 高度增大（抽屉向上展开）
  sheetHeight.value = clampSheetH(dragOrigin.startH - dy)
}

const onHandlePointerUp = () => {
  isDragging.value = false
  window.removeEventListener('pointermove', onHandlePointerMove)
  window.removeEventListener('pointerup', onHandlePointerUp)
  // 释放后按中点 snap 到最近档位
  const mid = (PEEK_H + expandedH()) / 2
  sheetHeight.value = sheetHeight.value > mid ? expandedH() : PEEK_H
}

const onHandleClick = () => {
  // 拖动产生的位移不触发切换
  if (dragMoved) return
  sheetHeight.value = sheetHeight.value > PEEK_H + 1 ? PEEK_H : expandedH()
}

// 移动端判定（沿用 MainLayout 的 ref + resize 监听模式，仓内无响应式 isMobile 组合式）
const isMobile = ref(false)
const updateIsMobile = () => { isMobile.value = window.innerWidth < 768 }

const onWindowResize = () => {
  updateIsMobile()
  if (isMobile.value) sheetHeight.value = clampSheetH(sheetHeight.value)
}

onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', onWindowResize)
  loadNation(props.startDate, props.endDate)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('pointermove', onHandlePointerMove)
  window.removeEventListener('pointerup', onHandlePointerUp)
})
</script>

<style scoped>
.animate-fade-in { animation: fadeIn 0.3s ease-in-out; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
