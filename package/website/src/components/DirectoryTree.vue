<template>
  <div class="space-y-2">
    <div v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">
      {{ error }} <el-button link type="primary" @click="retry">重试</el-button>
    </div>
    <div class="h-[300px] overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-900/50">
      <el-tree :key="revision" :props="treeProps" :load="loadNode" lazy highlight-current node-key="path" :current-node-key="modelValue" empty-text="无可选目录" @current-change="select">
        <template #default="{ data }"><div class="flex items-center gap-2 text-sm"><Folder class="h-4 w-4 text-primary-500" /><span>{{ data.name }}</span></div></template>
      </el-tree>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { Folder } from 'lucide-vue-next'
import { settingsApi } from '@/api/settings'
defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [path: string] }>()
const error = ref('')
const revision = ref(0)
const treeProps = { label: 'name', children: 'children', isLeaf: 'is_leaf' }
const select = (data: { path: string } | null) => emit('update:modelValue', data?.path || '')
const retry = () => { error.value = ''; revision.value++; emit('update:modelValue', '') }
const loadNode = async (node: { level: number; data: { path: string } }, resolve: (data: unknown[]) => void) => {
  try {
    const result = await settingsApi.getDirectoryTree(node.level === 0 ? undefined : node.data.path)
    resolve(result.directories || [])
  } catch { error.value = '加载目录失败'; resolve([]) }
}
</script>
