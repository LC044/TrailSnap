<template>
  <Teleport to="body">
    <div v-if="visible && showMobileHeader" class="selection-mobile-header" data-testid="photo-selection-header">
      <button class="ts-button ts-button-ghost" @click="$emit('select-all')">{{ isAllSelected ? '取消全选' : '全选' }}</button>
      <span class="font-semibold" aria-live="polite">已选 {{ selectionCount }} 项</span>
      <button class="ts-icon-button ts-button-ghost" aria-label="取消选择" @click="$emit('cancel')"><X class="h-5 w-5" /></button>
    </div>
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform translate-y-6 opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform translate-y-6 opacity-0"
    >
      <div v-if="visible" data-testid="photo-selection-bar" class="fixed bottom-[calc(var(--ts-tabbar-offset)_+_var(--ts-safe-area-bottom))] left-0 right-0 z-40 flex justify-center pointer-events-none px-3">
        <div class="ts-liquid-glass selection-toolbar pointer-events-auto">
          <div class="selection-summary flex items-center gap-2">
            <button @click="$emit('cancel')" class="ts-icon-button ts-button-ghost sm:p-2 hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-gray-300" title="取消选择" aria-label="取消选择">
              <X class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap text-sm sm:text-base">
              <span class="sm:hidden">已选 {{ selectionCount }} 项</span>
              <span class="hidden sm:inline">已选 {{ selectionCount }} 项</span>
            </span>
            <button @click="$emit('select-all')" class="ts-button ts-button-ghost selection-all" :title="isAllSelected ? '取消全选' : '全选'">
              <span class="">{{ isAllSelected ? '取消全选' : '全选' }}</span>

            </button>
          </div>

          <div class="hidden md:block h-6 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>

          <div class="selection-actions" :style="{ '--selection-action-columns': actionColumns }">
            <slot name="actions">


            <button
                @click="$emit('add-to-album', selectedArray)"
                :disabled="localSelectedIds.size === 0"
                class="ts-icon-button ts-button-ghost flex items-center gap-2 sm:px-4 sm:py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                title="添加到相册"
                >
                <ImagePlusIcon class="w-5 h-5" /><span>加入相册</span>
            </button>

            <!-- Download Action -->
            <button
              @click="$emit('download')"
              :disabled="localSelectedIds.size === 0 || isDownloading"
              class="ts-icon-button ts-button-ghost text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 disabled:opacity-50 disabled:cursor-not-allowed relative group"
              title="保存到本地"
            >
              <Loader2 v-if="isDownloading" class="w-5 h-5 animate-spin" />
              <Download v-else class="w-5 h-5" /><span>保存</span>
            </button>

            <!-- Delete/Remove Action -->
            <button
              @click="$emit('delete')"
              :disabled="localSelectedIds.size === 0"
              class="ts-icon-button ts-icon-danger text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              :title="deleteLabel"
            >
              <Trash2 class="w-5 h-5" /><span>{{ deleteLabel }}</span>
            </button>

            <!-- More Actions -->
            <el-dropdown trigger="click" placement="top-end">
              <button class="ts-icon-button ts-button-ghost text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800">
                <MoreHorizontal class="w-5 h-5" /><span>更多</span>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :disabled="localSelectedIds.size === 0" @click="$emit('person')">
                    <div class="flex items-center gap-2">
                      <UserPlus class="w-4 h-4" />
                      <span>添加到人物</span>
                    </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    :disabled="localSelectedIds.size === 0"
                    v-if="allowTransfer" @click="$emit('transfer', 'move', selectedArray)"
                  >
                     <div class="flex items-center gap-2">
                        <FolderOutput class="w-4 h-4" />
                        <span>移动到目录</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    :disabled="localSelectedIds.size === 0"
                    v-if="allowTransfer" @click="$emit('transfer', 'copy', selectedArray)"
                  >
                     <div class="flex items-center gap-2">
                        <Copy class="w-4 h-4" />
                        <span>复制到目录</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    v-if="albumContext"
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('remove-from-album', selectedArray)"
                  >
                     <div class="flex items-center gap-2">
                        <ImageMinusIcon class="w-4 h-4" />
                        <span>移出相册</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    v-if="albumContext && localSelectedIds.size===1"
                    @click="$emit('set-album-cover', selectedArray)"
                  >
                     <div class="flex items-center gap-2">
                        <ImageIcon class="w-4 h-4" />
                        <span>设为封面</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('batch-edit-location', selectedArray)"
                  >
                     <div class="flex items-center gap-2">
                        <MapPin class="w-4 h-4" />
                        <span>批量修正位置</span>
                     </div>
                  </el-dropdown-item>

                  <div class="border-t border-gray-100 dark:border-gray-800 my-1 mx-2" v-if="$slots['batch-actions']"></div>
                  <slot name="batch-actions" :selected-ids="localSelectedIds" :clear-selection="() => emit('cancel')"></slot>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            </slot>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>

</template>
<script setup lang="ts">
import { computed } from 'vue'
import { X, Download, Trash2, Loader2, ImageMinusIcon, ImagePlusIcon, MoreHorizontal, UserPlus, CheckSquare, FolderOutput, Copy, Image as ImageIcon, MapPin } from 'lucide-vue-next'
const props = withDefaults(defineProps<{
  visible: boolean
  selectedIds: ReadonlySet<string>
  isAllSelected: boolean
  isDownloading: boolean
  deleteLabel: string
  albumContext?: boolean
  allowTransfer?: boolean
  selectedCount?: number
  actionColumns?: number
  showMobileHeader?: boolean
}>(), { albumContext: false, allowTransfer: false, actionColumns: 4, showMobileHeader: true })
const localSelectedIds = computed(() => props.selectedIds)
const selectionCount = computed(() => props.selectedCount ?? props.selectedIds.size)
const selectedArray = computed(() => Array.from(props.selectedIds))
const emit = defineEmits<{
  cancel: []; 'select-all': []; download: []; delete: []; person: []
  'add-to-album': [ids: string[]]; 'remove-from-album': [ids: string[]]
  'set-album-cover': [ids: string[]]; 'batch-edit-location': [ids: string[]]
  transfer: [action: 'move' | 'copy', ids: string[]]
}>()
</script>

<style scoped>
.selection-mobile-header { display: none; }
.selection-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 24px; background: var(--ts-glass-panel); max-width: 100%; }
.selection-summary { flex-shrink: 0; }
.selection-actions { display: flex; gap: 4px; }
.selection-actions :deep(button) { width: auto; padding-inline: 12px; gap: 6px; font-size: 13px; }
@media (max-width: 767px) {
  .selection-mobile-header { position: fixed; top: 0; inset-inline: 0; z-index: 60; display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: calc(var(--ts-header-height) + var(--ts-safe-area-top)); padding: calc(8px + var(--ts-safe-area-top)) 12px 8px; background: var(--ts-glass-panel); color: var(--ts-color-text); border-bottom: 1px solid var(--ts-color-divider); backdrop-filter: blur(var(--ts-glass-blur-panel)); }
  .selection-toolbar { width: min(100%, 440px); padding: 6px; border-radius: var(--ts-radius-pill); }
  .selection-summary { display: none; }
  .selection-summary { width: 100%; }
  .selection-all { margin-left: auto; padding-inline: 12px; }
  .selection-actions { width: 100%; display: grid; grid-template-columns: repeat(var(--selection-action-columns, 4), minmax(0, 1fr)); }
  .selection-actions :deep(.el-dropdown) { display: block; min-width: 0; }
  .selection-actions :deep(button) { width: 100%; min-width: 0; height: 54px; flex-direction: column; gap: 3px; padding: 4px 0; font-size: 11px; }
}
</style>
