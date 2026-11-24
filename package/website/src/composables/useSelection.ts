import { ref, reactive, watch, onBeforeUnmount } from 'vue'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useUiStore } from '@/stores/uiStore'

export function useSelection() {
  const isSelectionMode = ref(false)
  const selectedIds = reactive(new Set<string>())
  // Shift 范围选择的锚点：普通点击（非 Shift）时移到最后点击的照片。
  const selectionAnchorId = ref<string | null>(null)
  const rangeAdditions = new Set<string>()
  let rangeRequest = 0

  const resetRange = (anchor: string | null = null) => {
    ++rangeRequest
    rangeAdditions.clear()
    selectionAnchorId.value = anchor
  }
  onBeforeUnmount(() => resetRange())

  // 同步到全局 UI 状态：移动端底部 Tab 栏 / Agent FAB 在选择模式激活时隐藏，
  // 避免与画廊底部批量操作条重叠。watch 可捕获直接对 isSelectionMode.value 赋值的路径。
  const uiStore = useUiStore()
  watch(isSelectionMode, (v) => uiStore.setSelectionActive(v))

  const enterSelectionMode = () => {
    isSelectionMode.value = true
  }

  const exitSelectionMode = () => {
    isSelectionMode.value = false
    selectedIds.clear()
    resetRange()
  }

  useOverlayStack(isSelectionMode, exitSelectionMode)

  const toggleSelectionMode = (val?: boolean) => {
    if (val !== undefined) {
      val ? enterSelectionMode() : exitSelectionMode()
    } else {
      isSelectionMode.value ? exitSelectionMode() : enterSelectionMode()
    }
  }

  const toggleSelect = (id: string) => {
    resetRange(id)
    if (selectedIds.has(id)) {
      selectedIds.delete(id)
    } else {
      selectedIds.add(id)
    }
  }

  const selectAll = (ids: string[]) => {
    resetRange()
    const allSelected = ids.every(id => selectedIds.has(id))
    if (allSelected) {
      // Deselect all provided ids
      ids.forEach(id => selectedIds.delete(id))
    } else {
      // Select all provided ids
      ids.forEach(id => selectedIds.add(id))
    }
  }

  const selectRange = async (
    orderedIds: () => string[],
    targetId: string,
    loadRange?: (anchor: string, target: string) => Promise<boolean> | undefined,
  ) => {
    const request = ++rangeRequest
    if (!selectionAnchorId.value) selectionAnchorId.value = targetId
    const anchor = selectionAnchorId.value
    const pending = loadRange?.(anchor, targetId)
    if (pending && !await pending) return
    if (request !== rangeRequest) return

    const ids = orderedIds()
    const endIndex = ids.indexOf(targetId)
    if (endIndex < 0) return
    const anchorIndex = ids.indexOf(anchor)
    if (anchorIndex < 0) selectionAnchorId.value = targetId
    const startIndex = anchorIndex < 0 ? endIndex : anchorIndex
    const nextRange = new Set(ids.slice(Math.min(startIndex, endIndex), Math.max(startIndex, endIndex) + 1))

    // 缩短连选时只撤回本轮 Shift 新增的照片，保留原有的独立选择。
    for (const id of rangeAdditions) {
      if (nextRange.has(id)) continue
      selectedIds.delete(id)
      rangeAdditions.delete(id)
    }
    for (const id of nextRange) {
      if (!selectedIds.has(id)) rangeAdditions.add(id)
      selectedIds.add(id)
    }
    enterSelectionMode()
  }

  const isSelected = (id: string) => selectedIds.has(id)

  return {
    isSelectionMode,
    selectedIds,
    resetRange,
    enterSelectionMode,
    exitSelectionMode,
    toggleSelectionMode,
    toggleSelect,
    selectAll,
    selectRange,
    isSelected
  }
}
