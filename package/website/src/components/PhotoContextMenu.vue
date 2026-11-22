<template>
  <AdaptiveMenu
    :model-value="target !== null"
    :point="point"
    title="照片操作"
    mobile-presentation="popover"
    @update:model-value="value => { if (!value) close() }"
  >
    <div ref="items" role="none" class="photo-context-items" @keydown="handleMenuKey">
      <div v-if="count > 1" class="photo-context-summary">已选 {{ count }} 项</div>
      <template v-if="count === 1 && allowViewing">
        <button type="button" role="menuitem" class="ts-action-row" @click="openViewer(false)"><Expand />打开</button>
        <button type="button" role="menuitem" class="ts-action-row" @click="openViewer(true)"><Info />查看详情</button>
      </template>
      <button v-if="!recycleBin" type="button" role="menuitem" class="ts-action-row" :disabled="isDownloading" @click="download">
        <Download />{{ count > 1 ? '下载所选' : '下载' }}
      </button>
      <button v-if="allowAddToAlbum" type="button" role="menuitem" class="ts-action-row" @click="apply('add-to-album')"><ImagePlus />加入相册</button>
      <button v-if="albumContext && count === 1" type="button" role="menuitem" class="ts-action-row" @click="apply('set-cover')"><ImageIcon />设为封面</button>
      <button v-if="removeLabel" type="button" role="menuitem" class="ts-action-row" @click="apply('remove')"><ImageMinus />{{ removeLabel }}</button>
      <button v-if="recycleBin" type="button" role="menuitem" class="ts-action-row" :disabled="busy" @click="apply('restore')"><RotateCcw />恢复</button>
      <button v-if="deleteLabel" type="button" role="menuitem" class="ts-action-row danger" :disabled="busy" @click="apply('delete')"><Trash2 />{{ deleteLabel }}</button>
    </div>
  </AdaptiveMenu>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, shallowRef } from 'vue'
import { Download, Expand, Image as ImageIcon, ImageMinus, ImagePlus, Info, RotateCcw, Trash2 } from 'lucide-vue-next'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import type { AlbumImage } from '@/types/album'

type Action = 'add-to-album' | 'set-cover' | 'remove' | 'restore' | 'delete'

const props = withDefaults(defineProps<{
  selectedIds?: ReadonlySet<string>
  selectedCount?: number
  allowViewing?: boolean
  allowAddToAlbum?: boolean
  albumContext?: boolean
  removeLabel?: string
  deleteLabel?: string
  recycleBin?: boolean
  busy?: boolean
  isDownloading?: boolean
}>(), { allowViewing: true })

const emit = defineEmits(['view', 'download', 'add-to-album', 'set-cover', 'remove', 'restore', 'delete'])

const target = shallowRef<{ photo: AlbumImage; ids: string[]; count: number; preserveSelection: boolean } | null>(null)
const point = shallowRef<{ x: number; y: number }>()
const items = ref<HTMLElement>()
const count = computed(() => target.value?.count ?? 0)
let previousFocus: HTMLElement | null = null

const close = () => { target.value = null }
const menuButtons = () => Array.from(items.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
const open = async (event: MouseEvent, photo: AlbumImage, allow = true) => {
  const touch = (event as PointerEvent).pointerType === 'touch'
    || (event as MouseEvent & { sourceCapabilities?: { firesTouchEvents: boolean } }).sourceCapabilities?.firesTouchEvents
  if (touch || event.button !== 2) {
    if (allow) event.preventDefault()
    return
  }
  if (!allow) return
  event.preventDefault()
  if (!target.value) previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const selection = props.selectedIds
  const forSelection = selection?.has(photo.id)
  const ids = selection && forSelection ? Array.from(selection) : [photo.id]
  const current = {
    photo,
    ids,
    count: forSelection ? props.selectedCount ?? ids.length : 1,
    preserveSelection: !forSelection && Boolean(selection?.size),
  }
  point.value = { x: event.clientX, y: event.clientY }
  target.value = current
  await nextTick()
  if (target.value === current) menuButtons()[0]?.focus({ preventScroll: true })
}

const handleMenuKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape' || event.key === 'Tab') {
    close()
    if (event.key === 'Escape') {
      event.stopPropagation()
      previousFocus?.focus({ preventScroll: true })
    }
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const buttons = menuButtons()
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
    : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
  buttons[next]?.focus()
}

const openViewer = (details: boolean) => {
  if (target.value) emit('view', target.value.photo, details)
  close()
}
const download = () => {
  if (target.value) emit('download', target.value.ids, target.value.photo)
  close()
}
const apply = (action: Action) => {
  if (target.value) emit(action, target.value.ids, target.value.preserveSelection)
  close()
}

defineExpose({ open })
</script>

<style scoped>
.photo-context-summary {
  padding: 5px 10px;
  color: var(--ts-color-text-secondary);
  font-size: 12px;
}
.photo-context-items .danger {
  margin-top: 3px;
  border-top: 1px solid var(--ts-color-divider);
}
</style>
