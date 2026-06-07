import { ref, computed } from 'vue'

const MAX_DEPTH = 30

export function useEditorHistory() {
  const stack = ref<string[]>([])
  const pointer = ref(-1)

  const canUndo = computed(() => pointer.value > 0)
  const canRedo = computed(() => pointer.value < stack.value.length - 1)

  function pushState(json: string) {
    // Discard any redo states beyond current pointer
    stack.value = stack.value.slice(0, pointer.value + 1)
    stack.value.push(json)
    if (stack.value.length > MAX_DEPTH) {
      stack.value.shift()
    }
    pointer.value = stack.value.length - 1
  }

  function undo(): string | null {
    if (!canUndo.value) return null
    pointer.value--
    return stack.value[pointer.value]
  }

  function redo(): string | null {
    if (!canRedo.value) return null
    pointer.value++
    return stack.value[pointer.value]
  }

  function reset() {
    stack.value = []
    pointer.value = -1
  }

  return { canUndo, canRedo, pushState, undo, redo, reset }
}
