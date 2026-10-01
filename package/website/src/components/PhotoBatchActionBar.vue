<template>
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-full opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform -translate-y-full opacity-0"
    >
      <div v-if="visible" data-testid="photo-selection-bar" class="fixed bottom-[20px] left-0 right-0 z-40 flex justify-center pointer-events-none px-4">
        <div class="bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border border-gray-200 dark:border-gray-700 shadow-lg rounded-full px-3 py-1 md:py-1 flex items-center gap-2 sm:gap-6 pointer-events-auto min-w-fit max-w-full overflow-x-auto scrollbar-hide">
          <div class="flex items-center gap-1 md:gap-3 flex-shrink-0">
            <button @click="$emit('cancel')" class="p-1.5 sm:p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors dark:text-gray-300 bg-transparent" title="取消选择">
              <X class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap text-sm sm:text-base">
              <span class="sm:hidden">{{ localSelectedIds.size }}</span>
              <span class="hidden sm:inline">已选 {{ localSelectedIds.size }} 项</span>
            </span>
          </div>

          <div class="h-6 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>

          <div class="flex items-center gap-1 sm:gap-2 flex-nowrap">
            <button @click="$emit('select-all')" class="p-2 sm:px-3 sm:py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors bg-transparent" :title="isAllSelected ? '取消全选' : '全选'">
              <span class="hidden sm:inline">{{ isAllSelected ? '取消全选' : '全选' }}</span>
              <CheckSquare class="w-5 h-5 sm:hidden" />
            </button>

            <button
                @click="$emit('add-to-album', selectedArray)"
                :disabled="localSelectedIds.size === 0"
                class="bg-transparent flex items-center gap-2 p-2 sm:px-4 sm:py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                title="添加到相册"
                >
                <ImagePlusIcon class="w-5 h-5" />
            </button>

            <!-- Download Action -->
            <button
              @click="$emit('download')"
              :disabled="localSelectedIds.size === 0 || isDownloading"
              class="bg-transparent p-2 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed relative group"
              title="保存到本地"
            >
              <Loader2 v-if="isDownloading" class="w-5 h-5 animate-spin" />
              <Download v-else class="w-5 h-5" />
            </button>

            <!-- Delete/Remove Action -->
            <button
              @click="$emit('delete')"
              :disabled="localSelectedIds.size === 0"
              class="bg-transparent p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              :title="deleteLabel"
            >
              <Trash2 class="w-5 h-5" />
            </button>

            <!-- More Actions -->
            <el-dropdown trigger="click" placement="top-end">
              <button class="bg-transparent p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
                <MoreHorizontal class="w-5 h-5" />
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
          </div>
        </div>
      </div>
    </transition>

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
}>(), { albumContext: false, allowTransfer: false })
const localSelectedIds = computed(() => props.selectedIds)
const selectedArray = computed(() => Array.from(props.selectedIds))
const emit = defineEmits<{
  cancel: []; 'select-all': []; download: []; delete: []; person: []
  'add-to-album': [ids: string[]]; 'remove-from-album': [ids: string[]]
  'set-album-cover': [ids: string[]]; 'batch-edit-location': [ids: string[]]
  transfer: [action: 'move' | 'copy', ids: string[]]
}>()
</script>
