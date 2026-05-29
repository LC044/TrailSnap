<template>
  <el-dialog
    v-model="visible"
    :title="action === 'move' ? '移动图片' : '复制图片'"
    width="500px"
    class="rounded-xl"
    :close-on-click-modal="false"
  >
    <div class="flex flex-col gap-4">
      <p class="text-sm text-gray-500 dark:text-gray-400">请选择目标外部文件夹。您可以直接在选中目录下创建新的子文件夹。</p>
      
      <div class="border border-gray-200 dark:border-gray-700 rounded-lg h-[300px] overflow-y-auto p-2 bg-gray-50 dark:bg-gray-900/50">
        <el-tree
          ref="treeRef"
          :props="defaultProps"
          :load="loadNode"
          lazy
          highlight-current
          @current-change="handleNodeClick"
          node-key="path"
          :empty-text="'无可选目录'"
        >
          <template #default="{ node, data }">
            <div class="flex items-center gap-2 text-sm">
              <Folder class="w-4 h-4 text-primary-500" />
              <span>{{ data.name }}</span>
            </div>
          </template>
        </el-tree>
      </div>

      <div class="flex flex-col gap-2">
        <label class="text-sm font-medium text-gray-700 dark:text-gray-300">子文件夹名称（可选）</label>
        <el-input 
          v-model="subFolderName" 
          placeholder="留空则直接放到选中的目录下" 
          clearable 
        />
      </div>
    </div>
    
    <template #footer>
      <div class="flex justify-end gap-3">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!selectedPath" @click="submit">确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Folder } from 'lucide-vue-next'
import { settingsApi } from '@/api/settings'
import { photoApi } from '@/api/photo'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  visible: boolean
  action: 'move' | 'copy'
  photoIds: string[]
  defaultSubFolder?: string
}>()

const emit = defineEmits(['update:visible', 'success'])

const visible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const treeRef = ref()
const selectedPath = ref('')
const subFolderName = ref('')
const submitting = ref(false)

const defaultProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'is_leaf'
}

watch(() => props.visible, (val) => {
  if (val) {
    selectedPath.value = ''
    subFolderName.value = props.defaultSubFolder || ''
  }
})

const loadNode = async (node: any, resolve: (data: any[]) => void) => {
  if (node.level === 0) {
    try {
      const res = await settingsApi.getDirectoryTree()
      resolve(res.directories || [])
    } catch (e) {
      resolve([])
    }
  } else {
    try {
      const res = await settingsApi.getDirectoryTree(node.data.path)
      resolve(res.directories || [])
    } catch (e) {
      resolve([])
    }
  }
}

const handleNodeClick = (data: any) => {
  selectedPath.value = data.path
}

const submit = async () => {
  if (!selectedPath.value) return
  
  let targetPath = selectedPath.value
  if (subFolderName.value.trim()) {
    // Replace backslashes with forward slashes for unified handling, then join
    targetPath = `${targetPath}/${subFolderName.value.trim()}`.replace(/\\/g, '/')
  }
  
  submitting.value = true
  try {
    await photoApi.transferPhotos(props.photoIds, targetPath, props.action)
    ElMessage.success(`${props.action === 'move' ? '移动' : '复制'}成功`)
    emit('success', props.action)
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}
</script>
