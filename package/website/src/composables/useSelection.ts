import { ref, reactive, computed, watch } from 'vue'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useUiStore } from '@/stores/uiStore'

export function useSelection() {
  const isSelectionMode = ref(false)
  const selectedIds = reactive(new Set<string>())
  // Shift 范围选择的锚点：普通点击（非 Shift）时移到最后点击的照片。
  const selectionAnchorId = ref<string | null>(null)

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
    selectionAnchorId.value = null
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
    if (selectedIds.has(id)) {
      selectedIds.delete(id)
    } else {
      selectedIds.add(id)
    }
  }

  const selectAll = (ids: string[]) => {
    const allSelected = ids.every(id => selectedIds.has(id))
    if (allSelected) {
      // Deselect all provided ids
      ids.forEach(id => selectedIds.delete(id))
    } else {
      // Select all provided ids
      ids.forEach(id => selectedIds.add(id))
    }
  }

  /**
   * 按画廊视觉顺序做范围选择/取消选择。
   *
   * ids 是调用方按当前布局整理好的有序 id 列表（如 props.photos 的扁平顺序）。
   * 语义与 macOS Finder 的 Shift 点击一致：整段被设置为与目标端相反的单一状态
   * （目标端原本未选中 → 整段选中；目标端已选中 → 整段取消），而不是逐项 toggle，
   * 这样重复 Shift 点击同一段不会来回抖动。
   */
  const selectRange = (ids: string[], targetId: string) => {
    if (!ids.length || !targetId) return
    const endIndex = ids.indexOf(targetId)
    if (endIndex < 0) return
    const anchor = selectionAnchorId.value ?? targetId
    const startIndex = anchor === targetId ? endIndex : ids.indexOf(anchor)
    if (!selectionAnchorId.value || startIndex < 0) selectionAnchorId.value = targetId
    const from = startIndex < 0 ? endIndex : Math.min(startIndex, endIndex)
    const to = startIndex < 0 ? endIndex : Math.max(startIndex, endIndex)
    const shouldSelect = !selectedIds.has(targetId)
    for (let i = from; i <= to; i++) {
      shouldSelect ? selectedIds.add(ids[i]) : selectedIds.delete(ids[i])
    }
  }

  const isSelected = (id: string) => selectedIds.has(id)

  return {
    isSelectionMode,
    selectedIds,
    selectionAnchorId,
    enterSelectionMode,
    exitSelectionMode,
    toggleSelectionMode,
    toggleSelect,
    selectAll,
    selectRange,
    isSelected
  }
}
