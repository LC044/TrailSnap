<template>
  <div class="absolute inset-0 z-[103] flex flex-col bg-black/95" @click.stop @keydown.esc="handleCancel">
    <!-- Top Bar -->
    <div class="flex items-center justify-between px-3 py-2 bg-gray-900/80 shrink-0">
      <div class="flex items-center gap-2">
        <button
          @click="handleCancel"
          class="w-8 h-8 md:w-10 md:h-10 flex items-center justify-center rounded-lg text-white/90 hover:bg-white/10 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          title="关闭"
        >
          <X class="w-5 h-5" />
        </button>
        <span class="text-white/70 text-sm hidden md:inline">编辑图片</span>
      </div>

      <div class="flex items-center gap-1">
        <button
          @click="editor.undo()"
          :disabled="!editor.canUndo.value"
          class="w-8 h-8 md:w-10 md:h-10 flex items-center justify-center rounded-lg text-white/90 hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          title="撤销 (Ctrl+Z)"
        >
          <Undo2 class="w-4 h-4" />
        </button>
        <button
          @click="editor.redo()"
          :disabled="!editor.canRedo.value"
          class="w-8 h-8 md:w-10 md:h-10 flex items-center justify-center rounded-lg text-white/90 hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          title="重做 (Ctrl+Shift+Z)"
        >
          <Redo2 class="w-4 h-4" />
        </button>

        <div class="w-px h-6 bg-white/20 mx-1"></div>

        <!-- Save Dropdown -->
        <el-dropdown trigger="click" @command="handleSave">
          <button
            :disabled="isSaving"
            class="h-8 md:h-10 px-3 flex items-center gap-1.5 rounded-lg bg-primary-500 text-white text-sm font-medium hover:bg-primary-600 transition-colors disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            <Save class="w-4 h-4" />
            <span class="hidden md:inline">{{ isSaving ? '保存中...' : '保存' }}</span>
            <ChevronDown class="w-3 h-3" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="replace">
                <div class="flex items-center gap-2">
                  <Replace class="w-4 h-4" />
                  <span>替换原图</span>
                </div>
              </el-dropdown-item>
              <el-dropdown-item command="new">
                <div class="flex items-center gap-2">
                  <FilePlus class="w-4 h-4" />
                  <span>另存为新图</span>
                </div>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <button
          @click="handleCancel"
          class="w-8 h-8 md:w-10 md:h-10 flex items-center justify-center rounded-lg text-white/70 hover:bg-white/10 hover:text-white/90 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          title="取消"
        >
          <X class="w-5 h-5" />
        </button>
      </div>
    </div>

    <!-- Canvas Area -->
    <div class="flex-1 flex items-center justify-center overflow-hidden relative" ref="canvasContainer">
      <div v-if="!editor.isReady.value" class="text-white/50 flex items-center gap-2">
        <Loader2 class="w-5 h-5 animate-spin" />
        <span>加载图片中...</span>
      </div>
      <canvas ref="canvasEl"></canvas>

      <!-- Crop action buttons -->
      <div v-if="editor.isCropping.value" class="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 z-10 flex-wrap justify-center">
        <!-- Ratio presets -->
        <button
          v-for="opt in cropRatios"
          :key="opt.label"
          @click="handleCropRatio(opt)"
          :class="[
            'px-3 py-1.5 rounded-md text-sm transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none',
            activeCropLabel === opt.label
              ? 'bg-primary-500 text-white'
              : 'bg-white/10 text-white/80 hover:bg-white/20',
          ]"
        >
          {{ opt.label }}
        </button>

        <div class="w-px h-6 bg-white/20 mx-1"></div>

        <button
          @click="editor.applyCrop()"
          class="px-4 py-1.5 rounded-md bg-primary-500 text-white text-sm font-medium hover:bg-primary-600 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          应用
        </button>
        <button
          @click="editor.cancelCrop()"
          class="px-4 py-1.5 rounded-md bg-white/10 text-white/90 text-sm hover:bg-white/20 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          取消
        </button>
      </div>
    </div>

    <!-- Bottom Toolbar -->
    <div class="px-2 py-2 bg-gray-900/80 shrink-0">
      <div class="flex items-center gap-1 flex-wrap justify-center">
        <!-- Tool Group -->
        <div class="flex items-center bg-white/5 rounded-lg p-0.5">
          <button
            v-for="tool in tools"
            :key="tool.id"
            @click="selectTool(tool.id)"
            :class="[
              'w-9 h-9 md:w-10 md:h-10 flex items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 focus-visible:outline-none',
              editor.activeTool.value === tool.id
                ? 'bg-primary-500/20 text-primary-400'
                : 'text-white/70 hover:bg-white/10 hover:text-white/90',
            ]"
            :title="tool.label"
          >
            <component :is="tool.icon" class="w-4 h-4" />
          </button>
        </div>

        <div class="w-px h-6 bg-white/20 mx-1"></div>

        <!-- Transform Group -->
        <div class="flex items-center bg-white/5 rounded-lg p-0.5">
          <button
            @click="startCropWithReset()"
            :disabled="editor.isCropping.value"
            :class="[
              'w-9 h-9 md:w-10 md:h-10 flex items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 focus-visible:outline-none',
              editor.isCropping.value
                ? 'bg-primary-500/20 text-primary-400'
                : 'text-white/70 hover:bg-white/10 hover:text-white/90',
            ]"
            title="裁剪"
          >
            <Crop class="w-4 h-4" />
          </button>
          <button
            @click="editor.rotate(90)"
            class="w-9 h-9 md:w-10 md:h-10 flex items-center justify-center rounded-md text-white/70 hover:bg-white/10 hover:text-white/90 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 focus-visible:outline-none"
            title="顺时针旋转90°"
          >
            <RotateCw class="w-4 h-4" />
          </button>
        </div>

        <div class="w-px h-6 bg-white/20 mx-1"></div>

        <!-- Style Controls -->
        <div class="flex items-center gap-2">
          <!-- Color Picker -->
          <div class="relative flex items-center">
            <el-color-picker
              v-model="colorValue"
              size="small"
              :predefine="presetColors"
              @change="editor.setDrawColor"
              class="editor-color-picker"
            />
          </div>

          <!-- Stroke Width -->
          <div class="flex items-center gap-1">
            <el-slider
              v-model="widthValue"
              :min="1"
              :max="20"
              :step="1"
              :show-tooltip="false"
              class="w-20 md:w-28"
              @input="editor.setStrokeWidth"
            />
          </div>

          <!-- Font Size (visible for text tool) -->
          <div v-if="editor.activeTool.value === 'text'" class="flex items-center gap-1">
            <span class="text-white/50 text-xs">字号</span>
            <el-slider
              v-model="fontSizeValue"
              :min="12"
              :max="72"
              :step="1"
              :show-tooltip="false"
              class="w-16 md:w-24"
              @input="editor.setFontSize"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, markRaw } from 'vue'
import {
  X, Undo2, Redo2, Save, ChevronDown,
  MousePointer2, Pen, Type, Square, Circle, Minus,
  Crop, RotateCw, FilePlus, Replace, Loader2,
} from 'lucide-vue-next'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useFabricEditor } from '@/composables/useFabricEditor'
import type { EditorTool } from '@/types/editor'
import { useHotkeys } from '@/composables/useHotkeys'
import { embedExifFromUrl } from '@/utils/exif'

const props = defineProps<{
  imageUrl: string
  imageWidth?: number
  imageHeight?: number
}>()

const emit = defineEmits<{
  save: [blob: Blob, filename: string, mode: 'replace' | 'new']
  cancel: []
}>()

const editor = useFabricEditor()
const canvasEl = ref<HTMLCanvasElement | null>(null)
const canvasContainer = ref<HTMLDivElement | null>(null)
const isSaving = ref(false)
const colorValue = ref('#ff0000')
const widthValue = ref(3)
const fontSizeValue = ref(24)
const currentCropRatio = ref<number | null>(null)
const activeCropLabel = ref('自由')

const cropRatios: { label: string; ratio: number | null }[] = [
  { label: '自由', ratio: null },
  { label: '原图', ratio: -1 }, // sentinel: compute from image
  { label: '1:1', ratio: 1 },
  { label: '4:3', ratio: 4 / 3 },
  { label: '3:4', ratio: 3 / 4 },
  { label: '16:9', ratio: 16 / 9 },
  { label: '9:16', ratio: 9 / 16 },
]

const presetColors = [
  '#ff0000', '#ff6600', '#ffcc00', '#00cc00', '#0066ff',
  '#9900cc', '#ffffff', '#000000',
]

const tools: { id: EditorTool; label: string; icon: any }[] = [
  { id: 'select', label: '选择 (V)', icon: markRaw(MousePointer2) },
  { id: 'draw', label: '画笔 (B)', icon: markRaw(Pen) },
  { id: 'text', label: '文字 (T)', icon: markRaw(Type) },
  { id: 'rect', label: '矩形 (R)', icon: markRaw(Square) },
  { id: 'ellipse', label: '椭圆 (E)', icon: markRaw(Circle) },
  { id: 'line', label: '直线 (L)', icon: markRaw(Minus) },
]

function startCropWithReset() {
  activeCropLabel.value = '自由'
  currentCropRatio.value = null
  editor.startCrop()
}

function selectTool(tool: EditorTool) {
  if (editor.isCropping.value) return
  editor.applyTool(tool)
}

function handleCropRatio(opt: { label: string; ratio: number | null }) {
  let ratio = opt.ratio
  // "原图" uses the actual image aspect ratio
  if (ratio === -1) {
    const c = editor.canvas.value
    ratio = c ? c.width! / c.height! : 16 / 9
  }
  activeCropLabel.value = opt.label
  currentCropRatio.value = ratio
  editor.setCropRatio(ratio)
}

let imageLoaded = false
let imageEl: HTMLImageElement | null = null

function loadImage() {
  if (!canvasEl.value || !canvasContainer.value) return
  imageEl = new Image()
  imageEl.crossOrigin = 'anonymous'
  imageEl.onload = () => {
    imageLoaded = true
    if (canvasEl.value) {
      editor.initCanvas(canvasEl.value, imageEl!)
      setupCanvasEvents()
    }
  }
  imageEl.onerror = () => {
    ElMessage.error('图片加载失败')
  }
  imageEl.src = props.imageUrl
}

function setupCanvasEvents() {
  const c = editor.canvas.value
  if (!c) return
  c.on('mouse:down', editor.handleCanvasMouseDown)
  c.on('mouse:move', editor.handleCanvasMouseMove)
  c.on('mouse:up', editor.handleCanvasMouseUp)
}

function handleSave(mode: 'replace' | 'new') {
  if (isSaving.value) return
  isSaving.value = true
  editor.exportToBlob('jpeg', 0.92).then(async (blob) => {
    // Canvas 导出会丢失全部 EXIF，这里从原图读取 EXIF 并重新嵌入编辑结果，
    // 以保留相机型号、GPS、拍摄时间等元数据（替换原图 & 另存为新图均生效）。
    let finalBlob = blob
    try {
      finalBlob = await embedExifFromUrl(props.imageUrl, blob)
    } catch (err) {
      console.warn('重新嵌入 EXIF 失败，将保存不含 EXIF 的图片:', err)
    }
    const ext = 'jpg'
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const filename = `edited_${timestamp}.${ext}`
    emit('save', finalBlob, filename, mode)
  }).catch((err) => {
    ElMessage.error('导出图片失败: ' + err.message)
  }).finally(() => {
    isSaving.value = false
  })
}

async function handleCancel() {
  if (editor.canUndo.value) {
    try {
      await ElMessageBox.confirm('有未保存的更改，确定要退出编辑吗？', '提示', {
        confirmButtonText: '退出',
        cancelButtonText: '继续编辑',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  emit('cancel')
}

// Editor hotkeys at priority 200 (higher than lightbox's 100)
useHotkeys([
  { key: 'z', handler: () => editor.undo(), ctrl: true },
  { key: 'z', handler: () => editor.redo(), ctrl: true, shift: true },
  { key: 'y', handler: () => editor.redo(), ctrl: true },
  { key: 'Delete', handler: () => { if (editor.activeTool.value === 'select') editor.deleteSelected() } },
  { key: 'Backspace', handler: () => { if (editor.activeTool.value === 'select') editor.deleteSelected() } },
  { key: 'Escape', handler: () => { if (editor.isCropping.value) editor.cancelCrop() } },
  { key: 'v', handler: () => selectTool('select') },
  { key: 'b', handler: () => selectTool('draw') },
  { key: 't', handler: () => selectTool('text') },
  { key: 'r', handler: () => selectTool('rect') },
  { key: 'e', handler: () => selectTool('ellipse') },
  { key: 'l', handler: () => selectTool('line') },
], { priority: 200 })

onMounted(() => {
  // Double nextTick to ensure container has layout dimensions
  nextTick(() => nextTick(loadImage))
})

onUnmounted(() => {
  editor.dispose()
  if (imageEl) {
    imageEl.onload = null
    imageEl.onerror = null
    imageEl.src = ''
    imageEl = null
  }
})
</script>
