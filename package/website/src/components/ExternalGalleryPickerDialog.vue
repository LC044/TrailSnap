<template>
  <el-dialog v-model="visible" title="选择服务端照片文件夹" width="min(620px, 92vw)" :close-on-click-modal="false">
    <p class="mb-3 text-sm text-gray-500 dark:text-gray-400">
      这里显示 TrailSnap Server 可见的 <code class="rounded bg-gray-100 px-1 dark:bg-gray-700">{{ root || '/app/Photos' }}</code> 目录树。
    </p>
    <div class="h-[360px] overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-900">
      <el-tree
        :props="treeProps"
        :load="loadNode"
        lazy
        highlight-current
        node-key="path"
        empty-text="没有可选目录，请先配置 Docker 挂载"
        @current-change="selectNode"
      >
        <template #default="{ data }">
          <span class="flex items-center gap-2 text-sm">
            <Folder class="h-4 w-4 text-primary-500" />
            <span>{{ data.name }}</span>
          </span>
        </template>
      </el-tree>
    </div>
    <p class="mt-3 break-all text-xs text-gray-500 dark:text-gray-400">当前选择：{{ selectedPath || '尚未选择' }}</p>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedPath"
        class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @click="confirm"
      >
        使用此文件夹
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Folder } from 'lucide-vue-next'
import { settingsApi } from '@/api/settings'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  select: [path: string]
}>()

const visible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value),
})
const selectedPath = ref('')
const root = ref('')
const treeProps = { label: 'name', children: 'children', isLeaf: 'is_leaf' }

watch(() => props.visible, value => {
  if (value) selectedPath.value = ''
})

const loadNode = async (node: any, resolve: (data: any[]) => void) => {
  try {
    if (node.level === 0) {
      const data = await settingsApi.browseExternalDirectories()
      root.value = data.root
      resolve([{
        name: data.root.split(/[\\/]/).filter(Boolean).pop() || data.root,
        path: data.root,
        is_leaf: false,
      }])
      return
    }
    const data = await settingsApi.browseExternalDirectories(node.data.path)
    resolve(data.directories || [])
  } catch {
    resolve([])
  }
}

const selectNode = (data: { path: string }) => { selectedPath.value = data.path }
const confirm = () => {
  if (!selectedPath.value) return
  emit('select', selectedPath.value)
  visible.value = false
}
</script>
