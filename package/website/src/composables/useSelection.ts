import { ref, reactive, computed, watch } from 'vue'
import { useUiStore } from '@/stores/uiStore'

export function useSelection() {
  const isSelectionMode = ref(false)
  const selectedIds = reactive(new Set<string>())

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
  }

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
  
  const isSelected = (id: string) => selectedIds.has(id)

  return {
    isSelectionMode,
    selectedIds,
    enterSelectionMode,
    exitSelectionMode,
    toggleSelectionMode,
    toggleSelect,
    selectAll,
    isSelected
  }
}
