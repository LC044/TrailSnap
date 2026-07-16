<template>
  <div class="folder-tree">
    <div v-if="loading" class="flex items-center gap-2 py-1.5 text-xs text-gray-400" :style="{ paddingLeft: indent + 'px' }">
      <Loader2 class="w-3.5 h-3.5 animate-spin" />
      <span>加载中…</span>
    </div>

    <template v-else>
      <div v-for="node in children" :key="node.path">
        <div
          class="group flex items-center gap-1 py-1.5 pr-2 rounded-lg cursor-pointer transition-colors select-none"
          :class="node.path === currentPath
            ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-300 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'"
          :style="{ paddingLeft: indent + 'px' }"
          @click="$emit('navigate', node.path)"
        >
          <!-- 展开/收起箭头 -->
          <button
            v-if="node.has_children"
            @click.stop="toggle(node)"
            class="flex-shrink-0 w-4 h-4 flex items-center justify-center rounded hover:bg-gray-200 dark:hover:bg-gray-700 bg-transparent p-0"
          >
            <ChevronRight class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-90': isExpanded(node.path) }" />
          </button>
          <span v-else class="flex-shrink-0 w-4"></span>

          <component :is="isExpanded(node.path) && node.has_children ? FolderOpen : Folder" class="w-4 h-4 flex-shrink-0 text-primary-500" />
          <span class="truncate text-sm flex-1" :title="node.name">{{ node.name }}</span>
          <span class="text-[10px] text-gray-400 dark:text-gray-500 flex-shrink-0">{{ node.count }}</span>
        </div>

        <!-- 递归子树 -->
        <FolderTree
          v-if="node.has_children && isExpanded(node.path)"
          :parent-path="node.path"
          :current-path="currentPath"
          :level="level + 1"
          @navigate="$emit('navigate', $event)"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Folder, FolderOpen, ChevronRight, Loader2 } from 'lucide-vue-next'
import { albumService } from '@/api/album'

interface FolderChild {
  name: string
  path: string
  count: number
  has_children: boolean
}

const props = withDefaults(defineProps<{
  parentPath?: string
  currentPath: string
  level?: number
}>(), {
  parentPath: '',
  level: 0
})

defineEmits<{ (e: 'navigate', path: string): void }>()

const children = ref<FolderChild[]>([])
const loading = ref(true)
const expanded = ref<Set<string>>(new Set())

const indent = computed(() => 8 + props.level * 14)

const isExpanded = (path: string) => expanded.value.has(path)
const toggle = (node: FolderChild) => {
  if (expanded.value.has(node.path)) expanded.value.delete(node.path)
  else expanded.value.add(node.path)
}

const load = async () => {
  loading.value = true
  try {
    const data = await albumService.getFolders(props.parentPath)
    children.value = data.children || []
    // 自动展开当前路径的祖先，使定位到当前所在文件夹
    for (const c of children.value) {
      if (props.currentPath === c.path || props.currentPath.startsWith(c.path + '/')) {
        expanded.value.add(c.path)
      }
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 当前路径变化时，补充展开新的祖先链
watch(() => props.currentPath, (cur) => {
  for (const c of children.value) {
    if (cur === c.path || cur.startsWith(c.path + '/')) {
      expanded.value.add(c.path)
    }
  }
})

onMounted(load)
</script>
